"""
OpportunityScout — Serendipity Engine

The "unexpected discovery" module. Unlike the scanner (which checks known sources)
and the generator (which invents models from accumulated data), the Serendipity
Engine lets Claude freely roam the internet with NO predefined source list.

It asks: "What's happening in the world right now that THIS specific founder
should know about — even if it's in a sector they've never considered?"

Two modes:
  - DAILY LIGHT: Sonnet + web search, broad trend scan, low cost (~$0.30/day)
  - WEEKLY DEEP: Opus + web search, deep cross-sector analysis (~$2-3/week)

Every finding goes through the standard 10-dimension scoring pipeline.
Only results with Founder Fit ≥ 5 survive — everything else is filtered out.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic

logger = logging.getLogger("scout.serendipity")

FOUNDER_PROFILE_PATH = Path("./config/founder_profile.yaml")
SYSTEM_PROMPT_PATH = Path("./SYSTEM_PROMPT.md")


class SerendipityEngine:
    """
    Discovers opportunities outside the operator's known sectors by
    letting Claude freely search the web with the founder's profile
    as the only filter.
    """

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.client = Anthropic(
            api_key=config.get('claude', {}).get('api_key')
            or os.environ.get('ANTHROPIC_API_KEY')
        )
        self.model_light = config.get('claude', {}).get(
            'model', 'claude-sonnet-4-20250514'
        )
        self.model_deep = config.get('claude', {}).get(
            'model_deep_dive', 'claude-opus-4-20250514'
        )
        self._founder_profile = self._load_file(FOUNDER_PROFILE_PATH)
        self._system_prompt = self._load_file(SYSTEM_PROMPT_PATH)
        self._min_founder_fit = config.get('serendipity', {}).get(
            'min_founder_fit', 5
        )

    # ─── Public API ─────────────────────────────────────────

    def daily_scan(self) -> dict:
        """
        DAILY LIGHT MODE: Quick broad scan using Sonnet.
        Cost: ~$0.30 per run.
        
        Asks Claude to search for today's most interesting business
        signals across ALL sectors and filter by founder fit.
        """
        logger.info("🎲 Serendipity daily scan starting...")

        # Build awareness context (what we already know, to avoid repeats)
        known_titles = self._get_known_titles(limit=30)
        known_tags = self._get_known_tags(limit=50)

        prompt = self._build_daily_prompt(known_titles, known_tags)

        try:
            response = self.client.messages.create(
                model=self.model_light,
                max_tokens=4096,
                system=self._system_prompt,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search"
                }],
                messages=[{"role": "user", "content": prompt}]
            )

            text = self._extract_text(response)
            results = self._parse_json_response(text)
            filtered = self._filter_by_founder_fit(results)

            # Store results
            stored = self._store_results(filtered, source_type="serendipity_daily")

            logger.info(
                f"🎲 Serendipity daily: {len(results.get('opportunities', []))} "
                f"found → {len(stored)} passed founder fit filter"
            )

            return {
                "mode": "daily_light",
                "raw_found": len(results.get('opportunities', [])),
                "passed_filter": len(stored),
                "opportunities": stored,
                "signals": results.get('signals', [])
            }

        except Exception as e:
            logger.error(f"Serendipity daily scan failed: {e}")
            return {"mode": "daily_light", "raw_found": 0,
                    "passed_filter": 0, "opportunities": [], "signals": []}

    def weekly_deep_scan(self) -> dict:
        """
        WEEKLY DEEP MODE: Thorough cross-sector analysis using Opus.
        Cost: ~$2-3 per run.
        
        Opus performs multi-step research:
        1. Scans for macro trends across all sectors
        2. Identifies structural shifts and emerging patterns  
        3. Cross-references each with the founder's capability map
        4. Designs specific opportunity angles for high-fit matches
        """
        logger.info("🎲 Serendipity weekly deep scan starting...")

        known_titles = self._get_known_titles(limit=50)
        known_tags = self._get_known_tags(limit=80)
        accumulated_context = self._get_accumulated_context()

        prompt = self._build_weekly_prompt(
            known_titles, known_tags, accumulated_context
        )

        try:
            response = self.client.messages.create(
                model=self.model_deep,
                max_tokens=8192,
                system=self._system_prompt,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search"
                }],
                messages=[{"role": "user", "content": prompt}]
            )

            text = self._extract_text(response)
            results = self._parse_json_response(text)
            filtered = self._filter_by_founder_fit(results)

            stored = self._store_results(filtered, source_type="serendipity_weekly")

            logger.info(
                f"🎲 Serendipity weekly: {len(results.get('opportunities', []))} "
                f"found → {len(stored)} passed founder fit filter"
            )

            return {
                "mode": "weekly_deep",
                "raw_found": len(results.get('opportunities', [])),
                "passed_filter": len(stored),
                "opportunities": stored,
                "signals": results.get('signals', []),
                "cross_pollinations": results.get('cross_pollinations', [])
            }

        except Exception as e:
            logger.error(f"Serendipity weekly scan failed: {e}")
            return {"mode": "weekly_deep", "raw_found": 0,
                    "passed_filter": 0, "opportunities": [], "signals": []}

    # ─── Prompt Builders ────────────────────────────────────

    def _build_daily_prompt(self, known_titles: list,
                            known_tags: list) -> str:
        """Build the daily light scan prompt."""
        avoid_section = ""
        if known_titles:
            avoid_section = (
                f"\n\nALREADY KNOWN — do NOT repeat these:\n"
                f"{chr(10).join(f'- {t}' for t in known_titles[:20])}\n"
            )

        known_sectors = ""
        if known_tags:
            known_sectors = (
                f"\n\nSECTORS ALREADY BEING MONITORED (look OUTSIDE these):\n"
                f"{', '.join(known_tags[:30])}\n"
            )

        return f"""You are the Serendipity Engine of OpportunityScout. Your job is to find business opportunities that the operator would NEVER find through their normal channels — because they exist in sectors, markets, or niches the operator doesn't even know to look at.

CRITICAL INSTRUCTION: You have web search available. USE IT AGGRESSIVELY. Search for:
- Today's biggest business news and emerging trends across ALL sectors
- New regulations creating compliance demand in unexpected places
- Technologies crossing from one industry into another
- Pricing arbitrage or supply chain gaps
- "Boring" industries being disrupted by AI
- One-person businesses generating surprising revenue
- Cross-border opportunities (especially UK ↔ Turkey ↔ UAE ↔ USA)
- Problems that AI just made 10x cheaper to solve

DO NOT limit yourself to construction, furniture, or any specific sector. Search broadly. The whole point is to find what the operator ISN'T looking for.

OPERATOR PROFILE (the filter, not the constraint):
{self._founder_profile}

After finding opportunities, score each one. ONLY include opportunities where Founder Fit ≥ 5 (the operator must have at least one relevant skill or asset).
{avoid_section}{known_sectors}
Search the web for at least 5 different broad queries covering different sectors and trend types. Then analyze what you find through the lens of this specific operator.

Return results in the standard JSON format with "opportunities", "signals", and "cross_pollinations" arrays. Tag each opportunity with "serendipity" plus relevant sector tags.

Remember: the BEST serendipity finds are ones where the operator says "I would never have thought of that, but actually... I could do that." The intersection of unexpected sector + existing capability = gold."""

    def _build_weekly_prompt(self, known_titles: list,
                             known_tags: list,
                             accumulated_context: str) -> str:
        """Build the weekly deep scan prompt."""
        avoid_section = ""
        if known_titles:
            avoid_section = (
                f"\n\nALREADY IN PORTFOLIO — avoid repeating:\n"
                f"{chr(10).join(f'- {t}' for t in known_titles[:30])}\n"
            )

        return f"""You are the Serendipity Engine running in DEEP MODE. This is the weekly cross-sector intelligence sweep. You have more time and budget — use it to go DEEP.

YOUR MISSION: Perform a comprehensive multi-step research process:

STEP 1 — MACRO TREND SCAN
Search the web for the biggest business, technology, regulatory, and economic trends happening RIGHT NOW across ALL sectors globally. Look at:
- AI breakthroughs crossing into new industries this week
- New regulations or policy changes creating compliance demand
- Supply chain disruptions or shifts creating arbitrage windows
- Industries where incumbents are weakening (layoffs, bankruptcies, poor earnings)
- Consumer behavior shifts creating new B2B service needs
- Geographic market openings (especially UK, Turkey, UAE, USA)
- Emerging "picks and shovels" plays
- Healthcare, fintech, legal tech, logistics, agriculture, energy, education — scan EVERYTHING

STEP 2 — STRUCTURAL ANALYSIS
For each macro trend, ask: "Is there a structural shift here that creates a persistent opportunity, or is this just news?" Filter for:
- Regulatory tailwinds (mandatory = recurring revenue)
- Technology cost curves crossing thresholds (what just became 10x cheaper?)
- Demographic shifts (aging, urbanization, migration patterns)
- Platform shifts (AI agents, voice, spatial computing)

STEP 3 — FOUNDER FIT CROSS-REFERENCE
Take every surviving trend and cross-reference it with this specific operator:

OPERATOR PROFILE:
{self._founder_profile}

For each trend, ask:
- Does ANY of the operator's skills, assets, or knowledge give them an edge here?
- Could Turkish manufacturing cost advantage apply?
- Could IT infrastructure expertise apply?
- Could construction domain knowledge apply in a non-obvious way?
- Could n8n/automation skills create a service offering?
- Could cross-border positioning create arbitrage?

ONLY include findings where Founder Fit ≥ 5.

STEP 4 — OPPORTUNITY DESIGN
For each high-fit finding, design a specific, actionable opportunity (not a vague trend). Include: who pays, how much, why now, and what the operator does in the next 48 hours to start.

ACCUMULATED INTELLIGENCE FROM RECENT SCANS:
{accumulated_context}
{avoid_section}

SEARCH EXTENSIVELY. Use at least 10 different web searches spanning different sectors, geographies, and trend types. The value of this module is BREADTH — finding what nobody else is looking for.

Return in standard JSON format with "opportunities", "signals", and "cross_pollinations" arrays. Tag everything with "serendipity" + sector tags. Include a "discovery_path" field in each opportunity explaining: what search led to this → what trend it connects to → why it fits this specific operator."""

    # ─── Filtering ──────────────────────────────────────────

    def _filter_by_founder_fit(self, results: dict) -> list:
        """
        Filter opportunities by Founder Fit score.
        Only opportunities with founder_fit >= threshold survive.
        """
        filtered = []
        for opp in results.get('opportunities', []):
            scores = opp.get('scores', {})
            ff = scores.get('founder_fit', {})
            ff_score = ff.get('score', 0) if isinstance(ff, dict) else (
                ff if isinstance(ff, (int, float)) else 0
            )
            if ff_score >= self._min_founder_fit:
                filtered.append(opp)
            else:
                logger.debug(
                    f"  Filtered out (FF={ff_score}): {opp.get('title', '?')}"
                )
        return filtered

    # ─── Storage ────────────────────────────────────────────

    def _store_results(self, opportunities: list, source_type: str) -> list:
        """Store serendipity findings in the knowledge base."""
        stored = []
        for opp in opportunities:
            # Ensure ID and metadata
            if not opp.get('id'):
                opp['id'] = (
                    f"SER-{datetime.utcnow().strftime('%Y%m%d')}-"
                    f"{len(stored)+1:03d}"
                )
            opp['source'] = source_type
            if 'serendipity' not in opp.get('tags', []):
                opp.setdefault('tags', []).append('serendipity')

            # Calculate weighted total if not present
            if not opp.get('weighted_total'):
                opp['weighted_total'] = self._calculate_weighted_total(
                    opp.get('scores', {})
                )
                opp['tier'] = self._determine_tier(opp['weighted_total'])

            if not self.kb.is_duplicate(opp.get('title', ''), source_type):
                self.kb.save_opportunity(opp)
                stored.append(opp)

        return stored

    # ─── Context Helpers ────────────────────────────────────

    def _get_known_titles(self, limit: int = 30) -> list:
        """Get titles of known opportunities to avoid repetition."""
        opps = self.kb.get_top_opportunities(limit=limit)
        return [o.get('title', '') for o in opps if o.get('title')]

    def _get_known_tags(self, limit: int = 50) -> list:
        """Get all tags currently in the knowledge base."""
        try:
            cursor = self.kb.conn.cursor()
            cursor.execute(
                "SELECT DISTINCT tags_json FROM opportunities "
                "WHERE tags_json IS NOT NULL LIMIT ?",
                (limit,)
            )
            all_tags = set()
            for row in cursor.fetchall():
                tags = json.loads(row[0] or '[]')
                all_tags.update(tags)
            return list(all_tags)
        except Exception:
            return []

    def _get_accumulated_context(self) -> str:
        """Get a summary of accumulated intelligence for the weekly prompt."""
        parts = []

        # Rising trends
        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT keyword, mention_count, trajectory
                FROM tracked_trends
                WHERE mention_count >= 2
                ORDER BY mention_count DESC LIMIT 20
            """)
            trends = cursor.fetchall()
            if trends:
                parts.append("RISING TRENDS FROM RECENT SCANS:")
                for t in trends:
                    arrow = {"rising": "↑", "stable": "→",
                             "declining": "↓"}.get(t[2], '?')
                    parts.append(f"  {arrow} {t[0]} (×{t[1]})")
        except Exception:
            pass

        # Recent blind spots
        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT description FROM evolution_log
                WHERE action_type = 'blind_spot'
                ORDER BY created_at DESC LIMIT 5
            """)
            spots = cursor.fetchall()
            if spots:
                parts.append("\nBLIND SPOTS DETECTED:")
                for s in spots:
                    parts.append(f"  👁️ {s[0]}")
        except Exception:
            pass

        # Top sectors by opportunity count
        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT sector, COUNT(*) as cnt, AVG(weighted_total) as avg_score
                FROM opportunities
                WHERE sector IS NOT NULL AND sector != ''
                GROUP BY sector
                ORDER BY cnt DESC LIMIT 10
            """)
            sectors = cursor.fetchall()
            if sectors:
                parts.append("\nSECTORS WITH MOST OPPORTUNITIES:")
                for s in sectors:
                    parts.append(f"  {s[0]}: {s[1]} opps, avg score {s[2]:.0f}")
        except Exception:
            pass

        return "\n".join(parts) if parts else "No accumulated data yet."

    # ─── Scoring Helpers ────────────────────────────────────

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

    def _parse_json_response(self, text: str) -> dict:
        """Extract JSON from Claude's response."""
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

        logger.warning("Could not parse JSON from serendipity response")
        return {"opportunities": [], "signals": [], "cross_pollinations": []}

    @staticmethod
    def _extract_text(response) -> str:
        """Extract text content from Claude API response."""
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
