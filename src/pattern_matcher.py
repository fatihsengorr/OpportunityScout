"""
OpportunityScout — Pattern Envanteri Matcher

For every opportunity, evaluate which of Fatih's 7 patterns are triggered.
Patterns come from Open Brain's `intelligence/pattern-framework` document
(12 Nisan 2026 strategic conversation).

Scoring:
  - 7 pattern × 0-1 score
  - ≥3 triggered = "high_match" (scoring bonus)
  - ≥5 triggered OR (Pattern #7 active + 2 others) = "wow_candidate"

The key insight: patterns measure Fatih's WAY OF SEEING and COMMITMENT CAPACITY,
not his skill inventory. They work across sectors — biotech, fintech, furniture
all alike. Pattern #7 (Commitment-Before-Capability) is the strongest and
overrides the minimum when active.
"""

import json
import logging
import yaml
from pathlib import Path
from .llm_router import LLMRouter

logger = logging.getLogger("scout.pattern_matcher")

PATTERNS_PATH = Path("./config/patterns.yaml")


class PatternMatcher:
    """Evaluate Fatih's 7 patterns for each opportunity."""

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.llm = LLMRouter(config)
        # Sonnet — pattern eval requires reasoning, cheapness secondary
        self.model = self.llm.get_model('scoring')
        self.patterns = self._load_patterns()
        self._ensure_schema()

    def _load_patterns(self) -> dict:
        try:
            return yaml.safe_load(PATTERNS_PATH.read_text(encoding='utf-8'))
        except FileNotFoundError:
            logger.error(f"patterns.yaml missing at {PATTERNS_PATH}")
            return {"patterns": [], "thresholds": {}}

    def _ensure_schema(self):
        cursor = self.kb.conn.cursor()
        cursor.execute("PRAGMA table_info(opportunities)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'pattern_matches_json' not in columns:
            cursor.execute(
                "ALTER TABLE opportunities ADD COLUMN pattern_matches_json TEXT"
            )
            cursor.execute(
                "ALTER TABLE opportunities ADD COLUMN pattern_count INTEGER DEFAULT 0"
            )
            cursor.execute(
                "ALTER TABLE opportunities ADD COLUMN pattern_verdict TEXT"
            )
            self.kb.conn.commit()

    # ─── Public API ─────────────────────────────────────────

    def match(self, opp: dict) -> dict:
        """Evaluate 7 patterns for a single opportunity.

        Returns:
          {
            "patterns": [{"id": 1, "name": "...", "matched": true, "confidence": 0.8, "reason": "..."}, ...],
            "count": 4,
            "verdict": "high_match" | "wow_candidate" | "weak",
            "bonus_multiplier": 1.07,
          }
        """
        title = opp.get('title', '')
        logger.info(f"🧬 Pattern matching: {title[:60]}...")

        # Build evaluation prompt
        prompt = self._build_prompt(opp)

        response = self.llm.create(
            model=self.model,
            max_tokens=2048,
            system="You are a strict pattern evaluator for a founder's opportunity filter. Return only valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text

        parsed = self._parse_json(text)
        if not parsed or 'patterns' not in parsed:
            logger.warning(f"Pattern match JSON parse failed for {opp.get('id', '?')}")
            return self._empty_result()

        return self._compute_verdict(parsed)

    def match_and_save(self, opp_id: str, opp: dict = None) -> dict:
        """Match patterns and persist to opportunities table.

        If opp is not provided, loads from KB.
        """
        if not opp:
            cursor = self.kb.conn.cursor()
            cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Opportunity {opp_id} not found")
            opp = dict(row)

        result = self.match(opp)

        cursor = self.kb.conn.cursor()
        cursor.execute("""
            UPDATE opportunities
            SET pattern_matches_json = ?,
                pattern_count = ?,
                pattern_verdict = ?,
                updated_at = datetime('now')
            WHERE id = ?
        """, (
            json.dumps(result, ensure_ascii=False),
            result.get('count', 0),
            result.get('verdict', 'weak'),
            opp_id,
        ))
        self.kb.conn.commit()

        logger.info(
            f"🧬 {opp_id}: {result['count']}/7 patterns — {result['verdict']} "
            f"(bonus ×{result['bonus_multiplier']})"
        )
        return result

    # ─── Prompt building ────────────────────────────────────

    def _build_prompt(self, opp: dict) -> str:
        """Build a focused evaluation prompt."""
        # Compact pattern summary
        pattern_list = []
        for p in self.patterns.get('patterns', []):
            pattern_list.append(
                f"### Pattern #{p['id']} — {p['name']}\n"
                f"{p['description']}\n"
                f"**Filtre sorusu:** {p['filter_question']}\n"
                f"**Pozitif sinyaller:** {'; '.join(p['positive_signals'][:3])}\n"
                f"**Negatif sinyaller:** {'; '.join(p['negative_signals'][:2])}"
            )
        patterns_text = "\n\n".join(pattern_list)

        title = opp.get('title', '?')
        one_liner = opp.get('one_liner', '')
        sector = opp.get('sector', '?')
        why_now = opp.get('why_now', '')
        first_move = opp.get('first_move', '')
        revenue_path = opp.get('revenue_path', '')

        return f"""Fatih'in 7 pattern envanterini bu iş fırsatına uygula. Her pattern için objektif bir eşleşme değerlendir.

FIRSAT:
Title: {title}
Özet: {one_liner}
Sektör: {sector}
Neden şimdi: {why_now}
İlk hamle: {first_move}
Gelir yolu: {revenue_path}

FATIH'İN 7 PATTERN ENVANTERİ:

{patterns_text}

GÖREV: Her pattern için:
1. Tetiklenip tetiklenmediğini değerlendir (matched: true/false)
2. Güven skorunu ver (confidence: 0.0-1.0)
3. Neden tetiklendiğini/tetiklenmediğini kısa açıkla (reason: 1 cümle)

KURALLAR:
- Kibar olma, ZORLU ol. Pattern sadece 3 ve üstü tetiklenmeli ki "high match" olsun.
- Jenerik eşleşme yapma — spesifik kanıt göster ya da ret et.
- Pattern #7 özel: "Fatih yaparım der mi?" sorusuna ancak gerçekten iddialı, öğrenme gerektiren fırsatlar için EVET de.
- Fırsat tamamen pasif yatırım ise tüm pattern'ler false olabilir (ve olmalı).

SADECE geçerli JSON döndür:

{{
  "patterns": [
    {{"id": 1, "matched": false, "confidence": 0.3, "reason": "..."}},
    {{"id": 2, "matched": true, "confidence": 0.8, "reason": "..."}},
    ...
    {{"id": 7, "matched": false, "confidence": 0.2, "reason": "..."}}
  ],
  "overall_reasoning": "2-3 cümle — bu fırsatın Fatih'in görme biçimine neden/nasıl oturduğu"
}}"""

    # ─── Verdict computation ────────────────────────────────

    def _compute_verdict(self, parsed: dict) -> dict:
        """Apply thresholds and compute bonus multiplier."""
        patterns = parsed.get('patterns', [])
        thresholds = self.patterns.get('thresholds', {})

        # Enrich each pattern with name (from config)
        pattern_index = {p['id']: p for p in self.patterns.get('patterns', [])}
        enriched = []
        for p in patterns:
            pid = p.get('id')
            meta = pattern_index.get(pid, {})
            enriched.append({
                'id': pid,
                'name': meta.get('name', f'Pattern {pid}'),
                'short': meta.get('short', ''),
                'matched': bool(p.get('matched', False)),
                'confidence': float(p.get('confidence', 0.0)),
                'reason': p.get('reason', ''),
            })

        count = sum(1 for p in enriched if p['matched'])
        pattern_7_active = any(
            p['matched'] and p['id'] == 7 for p in enriched
        )

        # Thresholds
        high_min = thresholds.get('high_match_minimum', 3)
        wow_min = thresholds.get('wow_candidate_minimum', 5)

        # Pattern #7 override: if #7 active + 2 others = wow candidate
        pattern_7_override = (
            self.patterns.get('pattern_7_override', {}).get('enabled', True)
            and pattern_7_active and count >= 3
        )

        # Verdict
        if count >= wow_min or pattern_7_override:
            verdict = 'wow_candidate'
        elif count >= high_min:
            verdict = 'high_match'
        else:
            verdict = 'weak'

        # Bonus multiplier
        bonuses = thresholds.get('bonus_multipliers', {})
        if count >= 7:
            mult = bonuses.get('all_7', 1.15)
        elif count == 6:
            mult = bonuses.get('six', 1.12)
        elif count == 5:
            mult = bonuses.get('five', 1.10)
        elif count == 4:
            mult = bonuses.get('four', 1.07)
        elif count == 3:
            mult = bonuses.get('three', 1.05)
        else:
            mult = bonuses.get('two_or_less', 1.0)

        return {
            'patterns': enriched,
            'count': count,
            'verdict': verdict,
            'bonus_multiplier': round(mult, 3),
            'pattern_7_active': pattern_7_active,
            'overall_reasoning': parsed.get('overall_reasoning', ''),
        }

    def _empty_result(self) -> dict:
        return {
            'patterns': [],
            'count': 0,
            'verdict': 'weak',
            'bonus_multiplier': 1.0,
            'pattern_7_active': False,
            'overall_reasoning': 'Parse error',
        }

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

    def format_summary(self, match: dict) -> str:
        """Human-readable badge for alerts."""
        count = match.get('count', 0)
        verdict = match.get('verdict', 'weak')
        icon = {
            'wow_candidate': '🎯',
            'high_match': '✓',
            'weak': '○',
        }.get(verdict, '?')
        return f"{icon} Patterns: {count}/7 ({verdict})"

    def format_full(self, match: dict) -> str:
        """Full pattern breakdown (for detail page / email)."""
        lines = [
            f"🧬 *Pattern Envanteri*: {self.format_summary(match)}",
            f"_Bonus:_ ×{match.get('bonus_multiplier', 1.0)}",
            "",
        ]
        for p in match.get('patterns', []):
            icon = '✅' if p['matched'] else '❌'
            conf_pct = int(p['confidence'] * 100)
            lines.append(
                f"{icon} *P{p['id']}. {p['name']}* ({conf_pct}%)"
            )
            if p.get('reason'):
                lines.append(f"   _{p['reason'][:150]}_")
        if match.get('overall_reasoning'):
            lines.append("")
            lines.append(f"*Genel:* {match['overall_reasoning']}")
        return "\n".join(lines)
