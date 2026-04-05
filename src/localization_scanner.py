"""
OpportunityScout — Localization Scanner (Samwer/Rocket Internet Lens)

The "copy what works" module. Inspired by the Samwer brothers' Rocket Internet
playbook: systematically scan for proven, funded, growing digital business
models globally — then check if they exist in the operator's target markets
(UK and Turkey). If not → localization opportunity.

This is fundamentally different thinking from the other modules:
  - Scanner: "What opportunities exist right now?"
  - Generator: "What new business should I invent?"
  - Serendipity: "What unexpected thing could I do?"
  - Localization: "What PROVEN model can I COPY into my markets?"

The risk profile is radically lower because the model is already validated
somewhere — the only question is whether it can be adapted.

Runs weekly (Opus for deep analysis + web search).
Cost: ~$2-3 per cycle.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic

logger = logging.getLogger("scout.localization")

FOUNDER_PROFILE_PATH = Path("./config/founder_profile.yaml")
SYSTEM_PROMPT_PATH = Path("./SYSTEM_PROMPT.md")


class LocalizationScanner:
    """
    Scans for proven business models globally and evaluates their
    localization potential for UK and Turkey markets.
    """

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.client = Anthropic(
            api_key=config.get('claude', {}).get('api_key')
            or os.environ.get('ANTHROPIC_API_KEY')
        )
        self.model = config.get('claude', {}).get(
            'model_deep_dive', 'claude-opus-4-20250514'
        )
        self._founder_profile = self._load_file(FOUNDER_PROFILE_PATH)
        self._system_prompt = self._load_file(SYSTEM_PROMPT_PATH)

    # ─── Public API ─────────────────────────────────────────

    def scan(self, focus_sector: str = None, count: int = 5) -> dict:
        """
        Run a full localization scan cycle.

        Phase 1: DISCOVER — Find successful, funded, growing models globally
        Phase 2: GAP CHECK — For each model, check UK and Turkey market presence
        Phase 3: FEASIBILITY — Score localization feasibility + founder fit
        Phase 4: ADAPT — Design specific adaptation plan for top candidates

        Args:
            focus_sector: Optional sector focus (e.g., "proptech", "healthtech")
            count: Number of localization opportunities to find (default 5)

        Returns:
            dict with "opportunities" list, each containing the original model,
            gap analysis, adaptation plan, and standard scoring.
        """
        logger.info(f"🌍 Localization scan starting"
                    f"{f' (focus: {focus_sector})' if focus_sector else ''}...")

        # Build context: what we already know, to avoid repeats
        known_titles = self._get_known_titles()
        previous_localizations = self._get_previous_localizations()

        # Single comprehensive Opus call with multi-phase prompt
        prompt = self._build_scan_prompt(
            known_titles, previous_localizations, focus_sector, count
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=self._system_prompt,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search"
                }],
                messages=[{"role": "user", "content": prompt}]
            )

            text = self._extract_text(response)
            results = self._parse_response(text)
            opportunities = results.get('opportunities', [])

            # Calculate scores and store
            stored = []
            for opp in opportunities:
                opp = self._finalize_opportunity(opp)
                if not self.kb.is_duplicate(opp.get('title', ''), 'localization_scanner'):
                    self.kb.save_opportunity(opp)
                    stored.append(opp)

            logger.info(f"🌍 Localization scan complete: {len(stored)} opportunities")

            return {
                "mode": "localization_scan",
                "focus_sector": focus_sector,
                "models_analyzed": len(opportunities),
                "opportunities_stored": len(stored),
                "opportunities": stored,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Localization scan failed: {e}")
            return {
                "mode": "localization_scan",
                "models_analyzed": 0,
                "opportunities_stored": 0,
                "opportunities": [],
                "error": str(e)
            }

    # ─── Prompt Builder ─────────────────────────────────────

    def _build_scan_prompt(self, known_titles: list,
                           previous_localizations: list,
                           focus_sector: str = None,
                           count: int = 5) -> str:
        """Build the comprehensive multi-phase localization prompt."""

        avoid_section = ""
        if known_titles:
            avoid_section += (
                "\n\nALREADY IN PORTFOLIO — do not repeat:\n"
                + "\n".join(f"- {t}" for t in known_titles[:30])
            )
        if previous_localizations:
            avoid_section += (
                "\n\nPREVIOUSLY ANALYZED LOCALIZATIONS — find NEW ones:\n"
                + "\n".join(f"- {t}" for t in previous_localizations[:20])
            )

        focus_instruction = ""
        if focus_sector:
            focus_instruction = (
                f"\n\nFOCUS CONSTRAINT: Prioritize models in or adjacent to: "
                f"{focus_sector}. But if you find an exceptional opportunity "
                f"outside this sector, include it.\n"
            )

        return f"""You are the Localization Scanner of OpportunityScout, implementing the Samwer brothers / Rocket Internet playbook with AI-era upgrades.

YOUR MISSION: Find {count} proven, funded, growing digital business models operating successfully OUTSIDE the UK and Turkey — that do NOT yet have a strong equivalent in the UK or Turkey. For each, design a specific localization strategy.

This is NOT about invention. This is about COPYING WHAT WORKS. The Samwer brothers built a $8B+ empire by systematically:
1. Finding successful US startups (Groupon, eBay, Zappos, Airbnb)
2. Cloning them for European/emerging markets
3. Executing faster than the original could expand
4. Either dominating the local market or selling to the original

In 2026, AI makes this 10x more powerful because:
- One person can now build what previously required a 20-person team
- AI agents can handle customer service, content, operations
- Cross-border arbitrage is amplified (Turkish dev costs, UK prices)
- Regulatory differences create natural moats (UK-specific compliance, Turkish market rules)

OPERATOR PROFILE:
{self._founder_profile}

TARGET MARKETS (in priority order):
1. United Kingdom — high purchasing power, English-speaking, operator relocating there
2. Turkey — operator's home market, deep network, low-cost operations base
3. Cross-border UK↔Turkey — unique arbitrage position
{focus_instruction}{avoid_section}

EXECUTE THIS 4-PHASE RESEARCH PROCESS:

═══ PHASE 1: DISCOVER ═══
Search the web extensively for:
- Recent Y Combinator batches (W2025, S2025, W2026) — find companies with traction
- Product Hunt top launches in the last 6 months with high upvotes
- TechCrunch / Crunchbase recent funding rounds ($1M-50M, Series A/B)
- Successful startups in: US, India, Brazil, Southeast Asia, Australia, Middle East, China
- Focus on models that are PROVEN (real revenue, real users) not just funded
- Look across ALL sectors: fintech, healthtech, edtech, proptech, logistics, food, HR, legal, insurance, marketplaces, SaaS tools, creator economy, climate tech, agritech

For each discovered model, note:
- Company name and country
- What they do (one sentence)
- Funding raised and revenue signals
- Why it works (what problem, what solution)
- Year founded and growth trajectory

═══ PHASE 2: GAP CHECK ═══
For each promising model, search specifically:
- "Is there a UK equivalent of [company name]?"
- "[Company's service] UK competitor alternative"
- "[Company's service] Turkey alternative Turkish"
- Check if the original company already operates in UK/Turkey

Classify each as:
- NO EQUIVALENT: Nothing similar exists in UK/Turkey → strongest opportunity
- WEAK EQUIVALENT: Something exists but is poorly executed, underfunded, or incomplete → still opportunity
- STRONG EQUIVALENT: A well-funded, established player already exists → skip
- ORIGINAL PRESENT: The original company already operates in UK/Turkey → skip

Only proceed with NO EQUIVALENT and WEAK EQUIVALENT models.

═══ PHASE 3: LOCALIZATION FEASIBILITY ═══
For each surviving model, evaluate:

A) REGULATORY FIT: Does UK/Turkey regulation help or hinder?
   - Could regulation create a MOAT? (e.g., UK data protection, Turkish banking rules)
   - Any licensing/compliance barriers to entry?

B) CULTURAL FIT: Does the model translate?
   - Consumer behavior differences
   - Payment preferences
   - Language requirements
   - Trust/brand dynamics

C) FOUNDER FIT: Can THIS specific operator execute this?
   - Which of their skills, assets, or networks apply?
   - Cross-border advantage applicable?
   - AI skills relevant for cost reduction?

D) ECONOMICS: Does the math work?
   - UK/Turkey pricing potential vs original market
   - Can it be built cheaper with AI + Turkish dev costs?
   - Market size in target market
   - Time to revenue estimate

═══ PHASE 4: ADAPTATION PLAN ═══
For the top {count} candidates, provide:

Return as JSON:
```json
{{
  "opportunities": [
    {{
      "id": "LOC-{{YYYYMMDD}}-{{N}}",
      "title": "Localized model name — [Original] for [Market]",
      "one_liner": "What this is in one sentence",
      "original_model": {{
        "company": "Original company name",
        "country": "Where it operates",
        "founded": "Year",
        "funding": "Total raised",
        "what_they_do": "One paragraph",
        "why_it_works": "Core insight",
        "revenue_signals": "Any known revenue/traction data",
        "url": "Company website"
      }},
      "gap_analysis": {{
        "uk_status": "NO_EQUIVALENT | WEAK_EQUIVALENT",
        "uk_competitors": "Any weak competitors found, or 'None found'",
        "turkey_status": "NO_EQUIVALENT | WEAK_EQUIVALENT",
        "turkey_competitors": "Any weak competitors found, or 'None found'",
        "why_gap_exists": "Why hasn't someone done this already in UK/TR?"
      }},
      "localization_plan": {{
        "target_market": "UK | Turkey | Both (UK first)",
        "key_adaptations": "What needs to change from the original model",
        "regulatory_advantage": "How UK/TR regulation helps or creates moat",
        "cultural_adaptations": "Language, UX, trust, payment changes needed",
        "ai_acceleration": "How AI makes this cheaper/faster to build than the original",
        "cross_border_angle": "How UK↔Turkey positioning creates advantage"
      }},
      "business_model": {{
        "revenue_type": "SaaS|Marketplace|Service|Product|Hybrid",
        "pricing": "Specific pricing for UK/TR market",
        "build_cost_estimate": "MVP cost estimate",
        "time_to_revenue": "Realistic estimate",
        "year_1_revenue_potential": "Conservative estimate"
      }},
      "founder_edge": "Why THIS operator, specifically?",
      "first_move": "Exact action in the next 48 hours",
      "week_1_plan": "Day-by-day first week",
      "kill_criteria": "What proves this won't work?",
      "confidence": "HIGH | MEDIUM | LOW",
      "confidence_reasoning": "Why?",
      "sector": "Primary sector",
      "geography": "UK | Turkey | Both",
      "tags": ["localization", "samwer-model", "sector-tag", "etc"],
      "scores": {{
        "founder_fit": {{"score": 8, "reason": "..."}},
        "ai_unlock": {{"score": 7, "reason": "..."}},
        "time_to_revenue": {{"score": 8, "reason": "..."}},
        "capital_efficiency": {{"score": 9, "reason": "..."}},
        "market_timing": {{"score": 7, "reason": "..."}},
        "defensibility": {{"score": 6, "reason": "..."}},
        "scale_potential": {{"score": 7, "reason": "..."}},
        "geographic_leverage": {{"score": 9, "reason": "..."}},
        "competition_gap": {{"score": 9, "reason": "..."}},
        "simplicity": {{"score": 7, "reason": "..."}}
      }}
    }}
  ]
}}
```

CRITICAL RULES:
- SEARCH EXTENSIVELY. Use at least 10 different web searches. This module's value comes from finding what nobody in UK/Turkey is looking at.
- Every original model must be REAL with verifiable funding/traction — no hypotheticals.
- The gap check must be THOROUGH — actually search for UK/Turkey competitors before claiming a gap.
- Cross-border angle (Turkish cost + UK revenue) should be evaluated for EVERY opportunity.
- AI acceleration should be specific: "Claude API for customer service" not "AI helps."
- Prioritize models that work with the operator's EXISTING skills (IT, automation, construction, manufacturing, cross-border trade).
- The best localization opportunities are often in BORING sectors that VCs in the original market have validated but UK/TR VCs haven't noticed yet.
- If you can't find {count} strong candidates, return fewer. Never pad with weak ideas."""

    # ─── Result Processing ──────────────────────────────────

    def _finalize_opportunity(self, opp: dict) -> dict:
        """Calculate weighted score and finalize opportunity for storage."""
        scores = opp.get('scores', {})
        opp['weighted_total'] = self._calculate_weighted_total(scores)
        opp['tier'] = self._determine_tier(opp['weighted_total'])
        opp['source'] = 'localization_scanner'

        if 'localization' not in opp.get('tags', []):
            opp.setdefault('tags', []).append('localization')
        if 'samwer-model' not in opp.get('tags', []):
            opp['tags'].append('samwer-model')

        # Flatten for knowledge base storage
        opp.setdefault('why_now', opp.get('gap_analysis', {}).get(
            'why_gap_exists', ''
        ))
        opp.setdefault('first_move', opp.get('first_move', ''))
        opp.setdefault('revenue_path', opp.get('business_model', {}).get(
            'pricing', ''
        ))
        opp.setdefault('risks', [opp.get('kill_criteria', 'Unknown')])
        opp.setdefault('sector', opp.get('sector', ''))
        opp.setdefault('geography', opp.get('geography', 'UK'))

        # Store rich data in source_date field for now
        # (full model data preserved in the opp dict for Telegram output)
        opp['source_date'] = datetime.utcnow().strftime('%Y-%m-%d')

        if not opp.get('id'):
            opp['id'] = (
                f"LOC-{datetime.utcnow().strftime('%Y%m%d')}-"
                f"{hash(opp.get('title', '')) % 1000:03d}"
            )

        return opp

    # ─── Context Helpers ────────────────────────────────────

    def _get_known_titles(self) -> list:
        opps = self.kb.get_top_opportunities(limit=30)
        return [o.get('title', '') for o in opps if o.get('title')]

    def _get_previous_localizations(self) -> list:
        """Get titles of previously found localization opportunities."""
        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT title FROM opportunities
                WHERE source = 'localization_scanner'
                ORDER BY created_at DESC LIMIT 20
            """)
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    # ─── Scoring ────────────────────────────────────────────

    def _calculate_weighted_total(self, scores: dict) -> float:
        weights = self.config.get('scoring', {}).get('weights', {
            'founder_fit': 3.0, 'ai_unlock': 2.5, 'time_to_revenue': 2.5,
            'capital_efficiency': 2.0, 'market_timing': 2.0,
            'defensibility': 1.5, 'scale_potential': 1.5,
            'geographic_leverage': 1.5, 'competition_gap': 1.0,
            'simplicity': 1.0
        })
        total = 0.0
        for dim, weight in weights.items():
            score_data = scores.get(dim, {})
            score = score_data.get('score', 0) if isinstance(score_data, dict) else (
                score_data if isinstance(score_data, (int, float)) else 0
            )
            total += score * weight
        return round(total, 1)

    def _determine_tier(self, weighted_total: float) -> str:
        thresholds = self.config.get('scoring', {}).get('tiers', {
            'fire': 150, 'high': 120, 'medium': 90
        })
        if weighted_total >= thresholds.get('fire', 150):
            return 'FIRE'
        elif weighted_total >= thresholds.get('high', 120):
            return 'HIGH'
        elif weighted_total >= thresholds.get('medium', 90):
            return 'MEDIUM'
        return 'LOW'

    # ─── Parsing ────────────────────────────────────────────

    def _parse_response(self, text: str) -> dict:
        import re
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        json_match = re.search(r'\{[\s\S]*"opportunities"[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse JSON from localization scan response")
        return {"opportunities": []}

    @staticmethod
    def _extract_text(response) -> str:
        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text
        return text

    @staticmethod
    def _load_file(path: Path) -> str:
        try:
            return path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return ""
