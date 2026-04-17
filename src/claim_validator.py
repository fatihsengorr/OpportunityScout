"""
OpportunityScout — Anti-Hallucination Claim Validator

Extract key factual claims from an opportunity and verify them via web search.
Claims like "X company raised $5M", "market is worth $2B", "Y regulation takes effect Q3"
are the fingerprints of hallucination — this module flags unverifiable ones.

Runs AFTER scoring, BEFORE final storage / alert dispatch.
Uses Claude Haiku (cheapest model with web_search) — ~$0.01-0.02 per opportunity.

Output stored in `opportunities.validation_json`:
  {
    "status": "verified" | "partial" | "unverified" | "disputed",
    "confidence": 0.0-1.0,
    "claims": [
      {"claim": "...", "status": "verified|unverified|disputed", "evidence": "..."},
      ...
    ],
    "flags": ["Unverified market size", ...]
  }
"""

import json
import logging
from datetime import datetime
from .llm_router import LLMRouter

logger = logging.getLogger("scout.validator")


class ClaimValidator:
    """Validate factual claims in opportunities before storage."""

    # How much to cost-bound validation per opportunity
    MAX_CLAIMS_PER_OPP = 3
    VALIDATION_MAX_TOKENS = 1024

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.llm = LLMRouter(config)
        # Validator explicitly uses Haiku — cheapest, web-search capable
        self.validation_model = "claude-haiku-4-5-20250514"
        # Fall back to whatever daily model if haiku not available
        self.fallback_model = self.llm.get_model('daily')
        self._ensure_schema()

    def _ensure_schema(self):
        cursor = self.kb.conn.cursor()
        cursor.execute("PRAGMA table_info(opportunities)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'validation_json' not in columns:
            cursor.execute("ALTER TABLE opportunities ADD COLUMN validation_json TEXT")
            cursor.execute("ALTER TABLE opportunities ADD COLUMN validated_at TEXT")
            self.kb.conn.commit()

    # ─── Public API ─────────────────────────────────────────

    def validate(self, opp: dict) -> dict:
        """Validate an opportunity's key claims.

        Returns validation dict — also stored if opp has an id.
        """
        title = opp.get('title', '')
        logger.info(f"🔎 Validating claims for: {title[:60]}...")

        # Step 1: Extract claims (single Claude call, no web search)
        claims = self._extract_claims(opp)
        if not claims:
            result = {
                'status': 'verified',
                'confidence': 1.0,
                'claims': [],
                'flags': [],
                'note': 'No verifiable claims detected',
                'validated_at': datetime.utcnow().isoformat(),
            }
            self._save(opp.get('id'), result)
            return result

        # Step 2: Validate each claim (Haiku + web search, multi-turn)
        validated = []
        for claim in claims[:self.MAX_CLAIMS_PER_OPP]:
            v = self._validate_single_claim(claim)
            validated.append(v)

        # Step 3: Aggregate (includes verifiability_score per Hassabis insight)
        result = self._aggregate(validated, opp)
        result['validated_at'] = datetime.utcnow().isoformat()

        self._save(opp.get('id'), result)

        logger.info(
            f"🔎 Validated {len(validated)} claims for {opp.get('id', '?')}: "
            f"{result['status']} (confidence {result['confidence']:.2f})"
        )
        return result

    # ─── Claim extraction ───────────────────────────────────

    def _extract_claims(self, opp: dict) -> list:
        """Extract 2-3 most important factual claims from opportunity text.

        Claims are specific, verifiable statements (numbers, names, dates).
        Returns empty list if nothing verifiable found.
        """
        # Gather all narrative fields
        text_parts = []
        for field in ('title', 'one_liner', 'description', 'why_now',
                      'revenue_path', 'first_move'):
            v = opp.get(field)
            if v:
                text_parts.append(str(v))
        narrative = ' | '.join(text_parts)[:3000]

        prompt = f"""Extract up to 3 specific, verifiable factual CLAIMS from this business opportunity text.

Claims MUST be specific and checkable — things like:
- "X company raised $5M Series A in 2025"
- "UK construction market is worth £XX billion"
- "Regulation Y takes effect on <date>"
- "Competitor Z charges £N/month for their product"

DO NOT extract:
- Opinions or predictions ("market will grow")
- Vague statements ("there is demand")
- Founder-side claims ("founder has 20 years experience")
- Generic trends without specifics

OPPORTUNITY TEXT:
{narrative}

Return ONLY valid JSON in this exact format:
{{"claims": ["claim 1", "claim 2", "claim 3"]}}

If no verifiable claims exist, return: {{"claims": []}}"""

        try:
            response = self.llm.create(
                model=self.validation_model,
                max_tokens=512,
                system="You are a fact-extraction expert. Return only valid JSON.",
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            # Haiku might not be available on all accounts — fallback
            logger.warning(f"Claim extraction with Haiku failed ({e}), falling back")
            response = self.llm.create(
                model=self.fallback_model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text

        parsed = self._parse_json(text)
        return parsed.get('claims', []) if isinstance(parsed, dict) else []

    # ─── Single claim validation (Haiku + web search) ─────────

    def _validate_single_claim(self, claim: str) -> dict:
        """Verify a single claim via web search.

        Returns {claim, status, evidence}.
        status ∈ {verified, unverified, disputed, inconclusive}
        """
        prompt = f"""Verify this factual CLAIM via web search:

CLAIM: "{claim}"

Search the web for direct evidence. Then respond with ONLY valid JSON:

{{
  "claim": "{claim}",
  "status": "verified" | "unverified" | "disputed" | "inconclusive",
  "evidence": "1-2 sentences citing sources",
  "sources": ["url or publication 1", "..."]
}}

Status definitions:
- verified: found authoritative source that directly confirms
- unverified: searched but could not find any evidence
- disputed: found evidence that contradicts the claim
- inconclusive: ambiguous — some support but also counter-signals"""

        messages = [{"role": "user", "content": prompt}]
        model = self.validation_model

        try:
            response = self.llm.create(
                model=model,
                max_tokens=self.VALIDATION_MAX_TOKENS,
                messages=messages,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
            )
        except Exception as e:
            logger.warning(f"Haiku validation failed ({e}), falling back to {self.fallback_model}")
            model = self.fallback_model
            response = self.llm.create(
                model=model,
                max_tokens=self.VALIDATION_MAX_TOKENS,
                messages=messages,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
            )

        # Multi-turn loop (capped at 3 searches — validation should be quick)
        loop_count = 0
        while response.stop_reason == "tool_use" and loop_count < 3:
            loop_count += 1
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if getattr(block, 'type', None) == "tool_use":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Search completed."
                    })
            messages.append({"role": "user", "content": tool_results})
            response = self.llm.create(
                model=model,
                max_tokens=self.VALIDATION_MAX_TOKENS,
                messages=messages,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
            )

        # Extract + parse
        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text

        parsed = self._parse_json(text)
        if not isinstance(parsed, dict) or 'status' not in parsed:
            return {
                'claim': claim,
                'status': 'inconclusive',
                'evidence': 'Parse failure',
                'sources': [],
            }
        # Normalize
        return {
            'claim': claim,
            'status': parsed.get('status', 'inconclusive'),
            'evidence': (parsed.get('evidence') or '')[:300],
            'sources': parsed.get('sources', [])[:3],
        }

    # ─── Verifiability scoring (Hassabis insight) ───────────

    def _compute_verifiability_score(self, opp: dict, validated: list) -> int:
        """Compute 1-10 verifiability score.

        Based on Hassabis's observation: "AI works best in domains with
        measurable feedback within 6-12 months." An opportunity that can
        produce measurable outcomes (revenue, user signups, regulatory
        pass/fail) scores high. Speculative academic claims score low.

        Factors:
        1. Revenue_path specificity (concrete timeline + amount)
        2. Validated claims ratio (how many stand up to web search)
        3. Disputed claims penalty
        4. "When will we know?" answerability
        """
        score = 5  # Base

        # Factor 1: Revenue path concreteness
        revenue_path = (opp.get('revenue_path') or '').lower()
        if revenue_path:
            # Has specific timeframe keywords
            timeframe_kws = ['30 gün', '60 gün', '90 gün', '6 ay', '12 ay',
                             '3 months', '6 months', '12 months', 'q1', 'q2',
                             'within', 'ilk', 'month']
            has_timeframe = any(kw in revenue_path for kw in timeframe_kws)
            # Has amount indicator
            has_amount = any(kw in revenue_path for kw in
                             ['£', '$', '₺', 'k/mo', 'mrr', 'arr', 'month',
                              'revenue', 'gelir', 'fatura'])
            if has_timeframe and has_amount:
                score += 2
            elif has_timeframe or has_amount:
                score += 1

        # Factor 2: First move concreteness
        first_move = (opp.get('first_move') or '').lower()
        if first_move and len(first_move) > 30:
            # Concrete action verbs
            concrete_kws = ['call', 'email', 'contact', 'ara', 'gönder',
                            'meet', 'demo', 'sign', 'onayla', 'post', 'yaz']
            if any(kw in first_move for kw in concrete_kws):
                score += 1

        # Factor 3: Validated claims influence
        if validated:
            total = len(validated)
            verified = sum(1 for v in validated if v.get('status') == 'verified')
            disputed = sum(1 for v in validated if v.get('status') == 'disputed')
            unverified = sum(1 for v in validated if v.get('status') == 'unverified')

            verified_ratio = verified / total
            if verified_ratio >= 0.66:
                score += 2
            elif verified_ratio >= 0.33:
                score += 1

            # Penalty for disputed or mostly unverified claims
            if disputed > 0:
                score -= 2
            if unverified >= total // 2:
                score -= 1

        # Factor 4: Sector modifier — some sectors inherently more verifiable
        sector = (opp.get('sector') or '').lower()
        inherently_verifiable = [
            'saas', 'marketplace', 'ecommerce', 'compliance',
            'manufacturing', 'logistics'
        ]
        speculative = ['research', 'ai-policy', 'philosophy', 'prediction']
        if any(s in sector for s in inherently_verifiable):
            score += 1
        elif any(s in sector for s in speculative):
            score -= 1

        # Clamp to 1-10
        return max(1, min(10, score))

    # ─── Aggregation ───────────────────────────────────────

    def _aggregate(self, validated: list, opp: dict = None) -> dict:
        """Aggregate per-claim validations into opp-level verdict."""
        if not validated:
            base = {
                'status': 'verified', 'confidence': 1.0,
                'claims': [], 'flags': [],
            }
            # Still compute verifiability_score from opp structure
            if opp:
                base['verifiability_score'] = self._compute_verifiability_score(opp, [])
            else:
                base['verifiability_score'] = 5
            return base

        counts = {'verified': 0, 'unverified': 0, 'disputed': 0, 'inconclusive': 0}
        for v in validated:
            counts[v.get('status', 'inconclusive')] = \
                counts.get(v.get('status', 'inconclusive'), 0) + 1

        total = len(validated)
        verified_ratio = counts['verified'] / total
        disputed_ratio = counts['disputed'] / total

        # Verdict
        if disputed_ratio > 0:
            status = 'disputed'
            confidence = 0.3
        elif verified_ratio >= 0.66:
            status = 'verified'
            confidence = 0.9
        elif verified_ratio >= 0.33:
            status = 'partial'
            confidence = 0.6
        else:
            status = 'unverified'
            confidence = 0.3

        flags = []
        for v in validated:
            if v.get('status') == 'disputed':
                flags.append(f"⚠️ Disputed: {v['claim'][:80]}")
            elif v.get('status') == 'unverified':
                flags.append(f"❓ Unverified: {v['claim'][:80]}")

        result = {
            'status': status,
            'confidence': confidence,
            'claims': validated,
            'flags': flags,
        }
        # Add verifiability_score (Hassabis insight)
        if opp:
            result['verifiability_score'] = self._compute_verifiability_score(opp, validated)
        return result

    # ─── Storage + parsing ─────────────────────────────────

    def _save(self, opp_id, validation: dict):
        if not opp_id:
            return
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            UPDATE opportunities
            SET validation_json = ?,
                validated_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = ?
        """, (json.dumps(validation, ensure_ascii=False), opp_id))
        self.kb.conn.commit()

    def _parse_json(self, text: str):
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

    def format_badge(self, validation: dict) -> str:
        """Short badge for inclusion in alerts — includes verifiability score."""
        status = validation.get('status', 'unverified')
        conf = validation.get('confidence', 0)
        verif = validation.get('verifiability_score', 0)
        emoji = {
            'verified': '✅',
            'partial': '🟡',
            'disputed': '❌',
            'unverified': '❓',
        }.get(status, '❓')
        verif_str = f" · V{verif}/10" if verif else ""
        return f"{emoji} {status} ({conf:.0%}){verif_str}"

    def format_full(self, validation: dict) -> str:
        """Full validation details."""
        lines = [
            f"🔎 *Claim Validation:* {self.format_badge(validation)}",
        ]
        claims = validation.get('claims', [])
        if not claims:
            lines.append("_No verifiable claims found._")
            return "\n".join(lines)
        for c in claims:
            s = c.get('status', '?')
            icon = {'verified': '✅', 'unverified': '❓',
                    'disputed': '❌', 'inconclusive': '⚪'}.get(s, '⚪')
            lines.append(f"\n{icon} *{c['claim'][:120]}*")
            if c.get('evidence'):
                lines.append(f"   {c['evidence'][:200]}")
        return "\n".join(lines)
