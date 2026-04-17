"""
OpportunityScout — Multi-Model Consensus Scorer

For FIRE-tier candidates, get an independent second opinion from a different
model than the one that originally scored the opportunity.

Strategy:
  - Primary score: whatever model scored it originally (usually Gemini Flash)
  - Second opinion: Claude Sonnet, scoring blind (no knowledge of primary score)
  - Agreement: if |primary - secondary| <= 15, accept primary as-is
  - Disagreement: flag 'score_disputed', use median, record both

Storage: opportunities.consensus_json
  {
    "primary": {"model": "gemini-2.5-flash", "score": 132, "tier": "FIRE"},
    "secondary": {"model": "claude-sonnet-4", "score": 98, "tier": "HIGH"},
    "median_score": 115,
    "disputed": true,
    "divergence": 34,
    "verdict": "downgraded"
  }

Cost: ~$0.05-0.10 per FIRE candidate (2nd Sonnet call, no web search)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from .llm_router import LLMRouter
from .scoring_utils import calculate_weighted_total, determine_tier

logger = logging.getLogger("scout.consensus")

FOUNDER_PROFILE_PATH = Path("./config/founder_profile.yaml")


# Divergence threshold: if two models differ by more than this, flag as disputed
DIVERGENCE_THRESHOLD = 15


class ConsensusScorer:
    """Cross-check FIRE-tier scores with an independent second opinion."""

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.llm = LLMRouter(config)

        # Second-opinion model is always different from primary model
        # Primary (scoring): Claude Sonnet (from get_model('scoring'))
        # Secondary: Gemini Flash — cheap, independent ecosystem, no shared priors
        self.secondary_model = "gemini-2.5-flash"
        self._founder_profile = self._load_text(FOUNDER_PROFILE_PATH)
        self._ensure_schema()

    def _load_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return ""

    def _ensure_schema(self):
        cursor = self.kb.conn.cursor()
        cursor.execute("PRAGMA table_info(opportunities)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'consensus_json' not in columns:
            cursor.execute("ALTER TABLE opportunities ADD COLUMN consensus_json TEXT")
            cursor.execute("ALTER TABLE opportunities ADD COLUMN score_disputed INTEGER DEFAULT 0")
            self.kb.conn.commit()

    # ─── Public API ─────────────────────────────────────────

    def check_consensus(self, opp: dict) -> dict:
        """Get an independent second opinion on an opportunity's score.

        Returns dict with primary score, secondary score, verdict, disputed flag.
        Also updates KB if opp has an id.
        """
        primary_score = float(opp.get('weighted_total', 0))
        primary_tier = opp.get('tier', 'LOW')
        primary_model = "original"  # We don't always know which model scored it

        logger.info(
            f"🧮 Consensus check for {opp.get('id', '?')[:20]}: "
            f"primary={primary_score:.0f} ({primary_tier})"
        )

        # Get independent second score (Gemini Flash — cheap, different ecosystem)
        try:
            secondary = self._score_secondary(opp)
        except Exception as e:
            logger.warning(f"Secondary scoring failed: {e}")
            return {
                'primary': {'model': primary_model, 'score': primary_score,
                            'tier': primary_tier},
                'secondary': None,
                'error': str(e),
                'disputed': False,
            }

        secondary_score = float(secondary.get('weighted_total', 0))
        secondary_tier = secondary.get('tier', 'LOW')

        divergence = abs(primary_score - secondary_score)
        disputed = divergence > DIVERGENCE_THRESHOLD
        median = round((primary_score + secondary_score) / 2, 1)

        # Verdict
        if not disputed:
            verdict = "agreement"
        elif secondary_score < primary_score:
            verdict = "downgraded_by_secondary"
        else:
            verdict = "upgraded_by_secondary"

        result = {
            'primary': {
                'model': primary_model,
                'score': primary_score,
                'tier': primary_tier,
            },
            'secondary': {
                'model': self.secondary_model,
                'score': secondary_score,
                'tier': secondary_tier,
                'reasoning': secondary.get('reasoning', ''),
            },
            'median_score': median,
            'divergence': round(divergence, 1),
            'disputed': disputed,
            'verdict': verdict,
            'checked_at': datetime.utcnow().isoformat(),
        }

        if opp.get('id'):
            self._save(opp['id'], result)

        if disputed:
            logger.warning(
                f"🧮 DISPUTED: {opp.get('id', '?')} — "
                f"primary={primary_score:.0f} vs secondary={secondary_score:.0f} "
                f"(Δ{divergence:.0f})"
            )
        else:
            logger.info(
                f"🧮 Consensus: median={median:.0f} (divergence {divergence:.0f})"
            )

        return result

    # ─── Secondary scoring (Gemini Flash, blind) ───────────

    def _score_secondary(self, opp: dict) -> dict:
        """Get an independent score from Gemini Flash.

        The model does NOT see the primary score — scores blind.
        """
        title = opp.get('title', '')
        one_liner = opp.get('one_liner', '')
        why_now = opp.get('why_now', '')
        first_move = opp.get('first_move', '')
        revenue_path = opp.get('revenue_path', '')
        sector = opp.get('sector', '?')

        # No mention of previous score — blind evaluation
        prompt = f"""Sen independent bir iş fırsatı değerlendiricisin. Aşağıdaki fırsatı 10-boyutlu skala ile değerlendir.

FIRSAT:
Title: {title}
Bir cümle: {one_liner}
Sektör: {sector}
Neden şimdi: {why_now}
İlk hamle: {first_move}
Gelir yolu: {revenue_path}

FOUNDER PROFILE:
{self._founder_profile[:1500]}

10 BOYUTU 1-10 ARASINDA PUANLA:

1. founder_fit (MULTIPLIER, additive değil): Founder'ın yetenekleriyle ne kadar uyumlu? (1-10)
   Bu boyut toplam skoru çarpar: total = base_total × (founder_fit / 10)
2. ai_unlock (×2.5): AI bu fırsatı olanaklı kılıyor mu yoksa geleneksel iş mi?
3. time_to_revenue (×2.5): 90 gün içinde para kazanabilir mi?
4. capital_efficiency (×2.0): Düşük sermaye ile başlatılabilir mi?
5. market_timing (×2.0): Şimdi mi? Yoksa çok erken/geç mi?
6. defensibility (×1.5): Birinci hamleyi yapan avantajı tutar mı?
7. scale_potential (×1.5): £1M+ ARR potansiyeli var mı?
8. geographic_leverage (×1.5): UK/TR/UAE cross-border avantajı işe yarıyor mu?
9. competition_gap (×1.0): Rekabet boşluğu gerçek mi?
10. simplicity (×1.0): Basit mi, karmaşık mı?

MAX base = 155. Çarpan ile max toplam da 155 (founder_fit=10 iken).

Return ONLY valid JSON:
{{
  "scores": {{
    "founder_fit": 0,
    "ai_unlock": 0,
    "time_to_revenue": 0,
    "capital_efficiency": 0,
    "market_timing": 0,
    "defensibility": 0,
    "scale_potential": 0,
    "geographic_leverage": 0,
    "competition_gap": 0,
    "simplicity": 0
  }},
  "reasoning": "2-3 cümle — bu fırsatın güçlü ve zayıf yönleri"
}}

KESİN ol, generic olma. Founder'ın gerçek yeteneklerine göre puanla."""

        response = self.llm.create(
            model=self.secondary_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text

        parsed = self._parse_json(text)
        if not parsed or 'scores' not in parsed:
            raise ValueError("Failed to parse secondary score")

        scores = parsed.get('scores', {})
        # Compute weighted total using same formula as primary
        weights = self.config.get('scoring', {}).get('weights', {})
        weighted_total = calculate_weighted_total(scores, weights)
        tiers = self.config.get('scoring', {}).get('tiers', {})
        tier = determine_tier(weighted_total, tiers)

        return {
            'scores': scores,
            'weighted_total': weighted_total,
            'tier': tier,
            'reasoning': parsed.get('reasoning', ''),
        }

    # ─── Storage + parsing ─────────────────────────────────

    def _save(self, opp_id: str, consensus: dict):
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            UPDATE opportunities
            SET consensus_json = ?,
                score_disputed = ?,
                updated_at = datetime('now')
            WHERE id = ?
        """, (json.dumps(consensus, ensure_ascii=False),
              1 if consensus.get('disputed') else 0,
              opp_id))
        self.kb.conn.commit()

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        import re
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        start = text.find('{')
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i+1])
                        except json.JSONDecodeError:
                            break
        return {}

    # ─── Rendering ──────────────────────────────────────────

    def format_badge(self, consensus: dict) -> str:
        """One-line badge for inclusion in alerts."""
        if not consensus or consensus.get('error'):
            return "⚪ consensus N/A"
        if consensus.get('disputed'):
            v = consensus.get('verdict', '')
            icon = '📉' if v == 'downgraded_by_secondary' else '📈'
            return (f"{icon} disputed (Δ{consensus.get('divergence', 0):.0f})")
        return f"✅ consensus agreement (Δ{consensus.get('divergence', 0):.0f})"

    def format_full(self, consensus: dict) -> str:
        """Full consensus details."""
        if not consensus:
            return "_No consensus check performed._"
        if consensus.get('error'):
            return f"⚠️ Consensus check failed: {consensus['error']}"

        p = consensus.get('primary', {})
        s = consensus.get('secondary', {}) or {}
        lines = [
            f"🧮 *Consensus Check*",
            f"• Primary ({p.get('model', '?')}): *{p.get('score', 0):.0f}/155* "
            f"({p.get('tier', '?')})",
        ]
        if s:
            lines.append(
                f"• Secondary ({s.get('model', '?')}): *{s.get('score', 0):.0f}/155* "
                f"({s.get('tier', '?')})"
            )
            lines.append(f"• Median: *{consensus.get('median_score', 0):.0f}/155*")
            lines.append(f"• Divergence: Δ{consensus.get('divergence', 0):.0f}")
            if consensus.get('disputed'):
                verdict = consensus.get('verdict', '')
                lines.append(f"• Verdict: *{verdict}*")
            else:
                lines.append(f"• Verdict: *{consensus.get('verdict', 'agreement')}*")
            if s.get('reasoning'):
                lines.append(f"\n_Second opinion:_ {s['reasoning'][:300]}")
        return "\n".join(lines)
