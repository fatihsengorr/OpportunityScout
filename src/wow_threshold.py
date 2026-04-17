"""
OpportunityScout — Vay (Wow) Threshold Evaluator

Second gate above FIRE tier. Opens only for genuinely "mature founder filter"
opportunities — per Fatih's 5 criteria from Open Brain's pattern-framework.

Criteria (each 0-1):
  1. Door — opens 5+ business doors (platform play)
  2. Scarcity — <100 people can do this globally, Fatih is one of them
  3. Scale — growth-oriented, not one-off
  4. Systematizable — wheel not rowing
  5. Role — builder not laborer

Pass threshold: ≥4/5 criteria met → VAY tier (above FIRE)
Prerequisite: Already FIRE tier + ≥5 patterns matched (or P7 + 3)

VAY tier triggers special 🌟 alert; annual target is 3-5 VAY opportunities.
"""

import json
import logging
import yaml
from pathlib import Path
from .llm_router import LLMRouter

logger = logging.getLogger("scout.wow")

WOW_CRITERIA_PATH = Path("./config/wow_criteria.yaml")


class WowThreshold:
    """Evaluate Fatih's 5 maturity criteria for FIRE candidates."""

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.llm = LLMRouter(config)
        self.model = self.llm.get_model('scoring')
        self.criteria_config = self._load_criteria()
        self._ensure_schema()

    def _load_criteria(self) -> dict:
        try:
            return yaml.safe_load(WOW_CRITERIA_PATH.read_text(encoding='utf-8'))
        except FileNotFoundError:
            logger.error(f"wow_criteria.yaml missing at {WOW_CRITERIA_PATH}")
            return {"criteria": [], "thresholds": {}}

    def _ensure_schema(self):
        cursor = self.kb.conn.cursor()
        cursor.execute("PRAGMA table_info(opportunities)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'wow_json' not in columns:
            cursor.execute("ALTER TABLE opportunities ADD COLUMN wow_json TEXT")
            cursor.execute("ALTER TABLE opportunities ADD COLUMN wow_pass INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE opportunities ADD COLUMN is_vay INTEGER DEFAULT 0")
            self.kb.conn.commit()

    # ─── Public API ─────────────────────────────────────────

    def evaluate(self, opp: dict) -> dict:
        """Evaluate 5 criteria; returns criterion results + verdict."""
        title = opp.get('title', '')
        logger.info(f"🌟 Wow eval: {title[:60]}...")

        # Pre-check: only evaluate FIRE tier with pattern support
        if not self._is_eligible(opp):
            return {
                'eligible': False,
                'reason': 'Not FIRE tier or insufficient patterns',
                'criteria': [],
                'pass_count': 0,
                'verdict': 'not_evaluated',
            }

        prompt = self._build_prompt(opp)

        response = self.llm.create(
            model=self.model,
            max_tokens=1536,
            system="You are a strict filter for mature-founder opportunities. Return only JSON.",
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text

        parsed = self._parse_json(text)
        if not parsed or 'criteria' not in parsed:
            logger.warning(f"Wow eval JSON parse failed for {opp.get('id', '?')}")
            return self._empty_result()

        return self._compute_verdict(parsed, opp)

    def evaluate_and_save(self, opp_id: str, opp: dict = None) -> dict:
        """Evaluate wow threshold and persist."""
        if not opp:
            cursor = self.kb.conn.cursor()
            cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Opportunity {opp_id} not found")
            opp = dict(row)

        result = self.evaluate(opp)

        cursor = self.kb.conn.cursor()
        cursor.execute("""
            UPDATE opportunities
            SET wow_json = ?,
                wow_pass = ?,
                is_vay = ?,
                updated_at = datetime('now')
            WHERE id = ?
        """, (
            json.dumps(result, ensure_ascii=False),
            result.get('pass_count', 0),
            1 if result.get('verdict') == 'VAY' else 0,
            opp_id,
        ))
        self.kb.conn.commit()

        logger.info(
            f"🌟 {opp_id}: {result.get('pass_count', 0)}/5 criteria — {result.get('verdict')}"
        )
        return result

    # ─── Eligibility check ──────────────────────────────────

    def _is_eligible(self, opp: dict) -> bool:
        """Only FIRE tier with strong pattern coverage gets evaluated."""
        tier = opp.get('tier', 'LOW')
        if tier != 'FIRE':
            return False

        # Check pattern coverage
        pattern_min = (self.criteria_config.get('pattern_prerequisite', {})
                       .get('min_pattern_count', 5))
        pattern_7_plus_three = (self.criteria_config.get('pattern_prerequisite', {})
                                .get('pattern_7_plus_three', True))

        pattern_count = opp.get('pattern_count', 0)
        pattern_matches = opp.get('pattern_matches_json')
        if isinstance(pattern_matches, str):
            try:
                pattern_matches = json.loads(pattern_matches)
            except Exception:
                pattern_matches = {}

        pattern_7_active = False
        if isinstance(pattern_matches, dict):
            for p in pattern_matches.get('patterns', []):
                if p.get('id') == 7 and p.get('matched'):
                    pattern_7_active = True
                    break

        # ≥5 patterns OR (P7 + 3 patterns)
        if pattern_count >= pattern_min:
            return True
        if pattern_7_plus_three and pattern_7_active and pattern_count >= 3:
            return True
        return False

    # ─── Prompt ─────────────────────────────────────────────

    def _build_prompt(self, opp: dict) -> str:
        """Build evaluation prompt."""
        criteria = self.criteria_config.get('criteria', [])
        criteria_text_parts = []
        for c in criteria:
            criteria_text_parts.append(
                f"### Kriter #{c['id']} — {c['name']}\n"
                f"{c['description']}\n"
                f"**Soru:** {c['pass_question']}\n"
                f"**Pozitif:** {'; '.join(c['positive_examples'][:2])}\n"
                f"**Negatif:** {'; '.join(c['negative_examples'][:2])}"
            )
        criteria_text = "\n\n".join(criteria_text_parts)

        return f"""Fatih'in 5 kriterli "olgun girişimci" filtresini bu FIRE tier fırsata uygula.

Bu fırsat zaten scoring'den FIRE çıkmış (weighted_total ≥ 125) ve pattern envanterinden
en az 5 pattern (ya da P7 + 3 pattern) tetiklemiş. Şimdi ikinci kapı: **Vay eşiği**.

FIRSAT:
Title: {opp.get('title', '?')}
Özet: {opp.get('one_liner', '')}
Sektör: {opp.get('sector', '?')}
Neden şimdi: {opp.get('why_now', '')}
İlk hamle: {opp.get('first_move', '')}
Gelir yolu: {opp.get('revenue_path', '')}

FATİH'İN 5 KRİTERLİ VAY ESİĞİ:

{criteria_text}

GÖREV: Her kriter için:
- PASS (true): Kriter belirgin şekilde karşılanıyor
- FAIL (false): Kriter karşılanmıyor
- Confidence (0.0-1.0) ve neden (1-2 cümle)

KURALLAR:
- ÇOK sıkı ol. Bu 'vay' tier'ıdır, yılda 3-5 fırsat. Binlerce FIRE'dan sadece VAY'a düşebilecek kalitede olanlar.
- Şüpheli kriterlerde FAIL ver. Net PASS olmayan PASS değildir.
- ≥4 PASS gerekir VAY tier alabilmek için. Bu eşik bilinçli yüksek.

SADECE valid JSON:

{{
  "criteria": [
    {{"id": 1, "pass": true, "confidence": 0.8, "reason": "..."}},
    {{"id": 2, "pass": false, "confidence": 0.7, "reason": "..."}},
    ...
    {{"id": 5, "pass": true, "confidence": 0.9, "reason": "..."}}
  ],
  "overall": "1-2 cümle — bu fırsatın Fatih'e 'vay' dedirtme potansiyeli"
}}"""

    # ─── Verdict ────────────────────────────────────────────

    def _compute_verdict(self, parsed: dict, opp: dict) -> dict:
        """Apply thresholds and return final verdict."""
        criteria = parsed.get('criteria', [])
        thresholds = self.criteria_config.get('thresholds', {})

        # Enrich each criterion with name
        criteria_index = {c['id']: c for c in self.criteria_config.get('criteria', [])}
        enriched = []
        for c in criteria:
            cid = c.get('id')
            meta = criteria_index.get(cid, {})
            enriched.append({
                'id': cid,
                'name': meta.get('name', f'Criterion {cid}'),
                'short': meta.get('short', ''),
                'pass': bool(c.get('pass', False)),
                'confidence': float(c.get('confidence', 0.0)),
                'reason': c.get('reason', ''),
            })

        pass_count = sum(1 for c in enriched if c['pass'])

        wow_min = thresholds.get('wow_pass_minimum', 4)
        near_min = thresholds.get('near_wow_minimum', 3)

        # Additional constraint: min weighted_total for VAY
        min_score = self.criteria_config.get('scoring', {}).get('vay_minimum_score', 140)
        weighted_total = float(opp.get('weighted_total', 0))

        if pass_count >= wow_min and weighted_total >= min_score:
            verdict = 'VAY'
        elif pass_count >= near_min:
            verdict = 'near_wow'
        else:
            verdict = 'fail'

        return {
            'eligible': True,
            'criteria': enriched,
            'pass_count': pass_count,
            'verdict': verdict,
            'weighted_total': weighted_total,
            'min_score_required': min_score,
            'overall': parsed.get('overall', ''),
        }

    def _empty_result(self) -> dict:
        return {
            'eligible': False,
            'criteria': [],
            'pass_count': 0,
            'verdict': 'fail',
            'overall': 'Parse error',
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

    def format_badge(self, result: dict) -> str:
        """One-line badge."""
        if not result.get('eligible'):
            return "⚪ wow N/A"
        verdict = result.get('verdict', 'fail')
        pc = result.get('pass_count', 0)
        if verdict == 'VAY':
            return f"🌟 VAY ({pc}/5 pass)"
        elif verdict == 'near_wow':
            return f"✨ near-wow ({pc}/5)"
        return f"○ wow fail ({pc}/5)"

    def format_full(self, result: dict) -> str:
        """Full breakdown."""
        if not result.get('eligible'):
            return f"_Not evaluated: {result.get('reason', 'ineligible')}_"

        lines = [
            f"🌟 *Vay Eşiği*: {self.format_badge(result)}",
            "",
        ]
        for c in result.get('criteria', []):
            icon = '✅' if c['pass'] else '❌'
            conf_pct = int(c['confidence'] * 100)
            lines.append(f"{icon} *{c['name']}* ({conf_pct}%)")
            if c.get('reason'):
                lines.append(f"   _{c['reason'][:200]}_")
        if result.get('overall'):
            lines.append("")
            lines.append(f"*Özet:* {result['overall']}")
        return "\n".join(lines)
