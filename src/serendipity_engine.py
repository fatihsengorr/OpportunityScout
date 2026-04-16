"""
OpportunityScout — Serendipity Engine v2 (4-Strategy Discovery Engine)

The "unexpected discovery" module, now powered by 4 parallel search strategies:

  Strategy 1: SIGNAL CHASING — Event-reactive, follows fresh intelligence leads
  Strategy 2: CONTRARIAN SEARCH — Looks where nobody else is looking
  Strategy 3: BUYER JOURNEY MINING — Starts from demand, maps buyer spend gaps
  Strategy 4: FRONTIER SCANNER — Catches emerging tech × founder skills intersections

Each strategy runs independently, produces scored opportunities, and logs
performance metrics for the self-improver to optimize over time.

Two modes:
  - DAILY LIGHT: All 4 strategies run with Sonnet, fast queries (~$0.75/day)
  - WEEKLY DEEP: All 4 strategies run with Opus, deep research (~$3/week)
"""

import json
import logging
import time
import uuid
import yaml
from datetime import datetime
from pathlib import Path
from .llm_router import LLMRouter
from src.scoring_utils import calculate_weighted_total, determine_tier

logger = logging.getLogger("scout.serendipity")

FOUNDER_PROFILE_PATH = Path("./config/founder_profile.yaml")
SYSTEM_PROMPT_PATH = Path("./SYSTEM_PROMPT.md")
SECTOR_ROTATION_PATH = Path("./config/sector_rotation.yaml")


class SerendipityEngine:
    """
    4-Strategy Discovery Engine.
    Discovers opportunities outside the operator's known sectors by
    running 4 fundamentally different search strategies in parallel.
    """

    STRATEGY_NAMES = [
        'signal_chasing',
        'contrarian',
        'buyer_journey',
        'frontier_scanner'
    ]

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.llm = LLMRouter(config)
        self.model_light = self.llm.get_model('daily')
        self.model_deep = self.llm.get_model('weekly')
        self._founder_profile = self._load_file(FOUNDER_PROFILE_PATH)
        self._system_prompt = self._load_file(SYSTEM_PROMPT_PATH)
        self._min_founder_fit = config.get('serendipity', {}).get(
            'min_founder_fit', 5
        )
        self._sector_rotation = self._load_sector_rotation()

    # ═══════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════

    def daily_scan(self) -> dict:
        """
        DAILY LIGHT MODE: All 4 strategies run with Sonnet.
        Cost: ~$0.75 per run.
        """
        logger.info("🎲 Serendipity 4-strategy daily scan starting...")
        return self._run_all_strategies(mode="daily", model=self.model_light,
                                         max_tokens=4096, max_loops=15)

    def weekly_deep_scan(self) -> dict:
        """
        WEEKLY DEEP MODE: All 4 strategies run with Opus.
        Cost: ~$3 per run.
        """
        logger.info("🎲 Serendipity 4-strategy weekly deep scan starting...")
        return self._run_all_strategies(mode="weekly", model=self.model_deep,
                                         max_tokens=8192, max_loops=25)

    # ═══════════════════════════════════════════════════════════
    # ORCHESTRATOR
    # ═══════════════════════════════════════════════════════════

    def _run_all_strategies(self, mode: str, model: str,
                            max_tokens: int, max_loops: int) -> dict:
        """Run all 4 strategies sequentially, collect and merge results."""
        known_titles = self._get_known_titles(limit=50)
        known_tags = self._get_known_tags(limit=80)
        accumulated_context = self._get_accumulated_context()
        rotation = self._get_current_rotation()

        all_opportunities = []
        all_signals = []
        strategy_results = {}

        strategies = [
            ('signal_chasing', self._strategy_signal_chasing),
            ('contrarian', self._strategy_contrarian),
            ('buyer_journey', self._strategy_buyer_journey),
            ('frontier_scanner', self._strategy_frontier_scanner),
        ]

        for strategy_name, strategy_fn in strategies:
            start_time = time.time()
            logger.info(f"🎲 Running strategy: {strategy_name}")

            try:
                result = strategy_fn(
                    model=model,
                    max_tokens=max_tokens,
                    max_loops=max_loops,
                    known_titles=known_titles,
                    known_tags=known_tags,
                    accumulated_context=accumulated_context,
                    rotation=rotation
                )

                opps = result.get('opportunities', [])
                signals = result.get('signals', [])
                duration = time.time() - start_time

                # Store and filter
                stored = self._store_results(opps, f"serendipity_{strategy_name}")

                # Track performance
                fire_count = len([o for o in stored if o.get('tier') == 'FIRE'])
                high_count = len([o for o in stored if o.get('tier') == 'HIGH'])
                scores = [o.get('weighted_total', 0) for o in stored]
                avg_score = sum(scores) / len(scores) if scores else 0
                best_score = max(scores) if scores else 0

                self.kb.log_strategy_performance(
                    engine='serendipity',
                    strategy_name=strategy_name,
                    opportunities_found=len(stored),
                    avg_score=round(avg_score, 1),
                    best_score=best_score,
                    fire_count=fire_count,
                    high_count=high_count,
                    duration_seconds=round(duration, 1)
                )

                strategy_results[strategy_name] = {
                    'raw_found': len(opps),
                    'stored': len(stored),
                    'fire': fire_count,
                    'high': high_count,
                    'best_score': best_score,
                    'avg_score': round(avg_score, 1),
                    'duration': round(duration, 1)
                }

                all_opportunities.extend(stored)
                all_signals.extend(signals)

                # Add stored titles to known list to avoid cross-strategy dupes
                known_titles.extend([o.get('title', '') for o in stored])

                logger.info(
                    f"🎲 {strategy_name}: {len(opps)} raw → {len(stored)} stored "
                    f"(🔥{fire_count} ⭐{high_count}) in {duration:.0f}s"
                )

            except Exception as e:
                logger.error(f"🎲 Strategy {strategy_name} failed: {e}")
                strategy_results[strategy_name] = {'error': str(e)}

        # Build summary
        total_stored = len(all_opportunities)
        total_fire = sum(r.get('fire', 0) for r in strategy_results.values() if isinstance(r, dict))
        total_high = sum(r.get('high', 0) for r in strategy_results.values() if isinstance(r, dict))

        logger.info(f"{'='*50}")
        logger.info(f"🎲 SERENDIPITY 4-STRATEGY {mode.upper()} COMPLETE")
        logger.info(f"   Total: {total_stored} opps (🔥{total_fire} ⭐{total_high})")
        for name, r in strategy_results.items():
            if isinstance(r, dict) and 'error' not in r:
                logger.info(f"   {name}: {r['stored']} opps, best={r['best_score']}")
        logger.info(f"{'='*50}")

        return {
            "mode": f"{mode}_4strategy",
            "raw_found": sum(r.get('raw_found', 0) for r in strategy_results.values() if isinstance(r, dict)),
            "passed_filter": total_stored,
            "opportunities": all_opportunities,
            "signals": all_signals,
            "strategy_results": strategy_results
        }

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 1: SIGNAL CHASING (Event-Reactive)
    # ═══════════════════════════════════════════════════════════

    def _strategy_signal_chasing(self, model: str, max_tokens: int,
                                  max_loops: int, **kwargs) -> dict:
        """
        Follow fresh intelligence leads from the event bus.
        If no events, falls back to searching for latest breaking signals.
        """
        # Get unprocessed events from KB
        events = self.kb.get_unprocessed_events(limit=10)
        signal_events = [e for e in events if e.get('event_type') in
                         ('signal_detected', 'blind_spot_found', 'deadline_approaching')]

        if signal_events:
            # Build targeted searches from events
            event_summaries = []
            event_ids = []
            for ev in signal_events[:5]:
                data = ev.get('data', {})
                summary = data.get('summary', '') or data.get('description', '') or str(data)
                event_summaries.append(f"- [{ev['event_type']}] {summary[:200]}")
                event_ids.append(ev.get('id'))

            prompt = f"""You are the Signal Chasing strategy of OpportunityScout's Serendipity Engine.

MISSION: Follow up on these FRESH intelligence signals and find specific business opportunities.

FRESH SIGNALS TO INVESTIGATE:
{chr(10).join(event_summaries)}

For EACH signal:
1. Search the web for the latest developments related to this signal
2. Identify WHO is affected, WHAT they need, and HOW MUCH they'd pay
3. Design a specific business opportunity that leverages the operator's capabilities

OPERATOR CAPABILITIES:
{self._founder_profile}

ALREADY KNOWN (avoid repeats):
{chr(10).join(f'- {t}' for t in kwargs.get('known_titles', [])[:15])}

Search the web for at least 3 targeted queries based on these signals.

CRITICAL: Your ENTIRE response must be ONLY a valid JSON object. No text before or after.
Format: {{"opportunities": [...], "signals": [...], "cross_pollinations": [...]}}
Include "action_by" date (YYYY-MM-DD or null) for time-sensitive opportunities.

Score each opportunity using the 10-dimension model. Only include founder_fit >= 5."""

            # Mark events as processed
            for eid in event_ids:
                if eid:
                    self.kb.mark_event_processed(eid)
        else:
            # Fallback: search for today's breaking business signals
            prompt = f"""You are the Signal Chasing strategy of OpportunityScout's Serendipity Engine.

MISSION: Find TODAY's freshest, most time-sensitive business signals.

Search the web for:
1. Breaking regulatory announcements (any sector, any country in UK/EU/US/UAE/TR)
2. Major funding rounds or acquisitions announced this week
3. New government tenders or framework agreements
4. Technology launches that just became commercially available
5. Market disruptions or company failures creating gaps

For each signal found, immediately ask: "How could someone with these capabilities profit from this?"

OPERATOR CAPABILITIES (brief):
- 20yr IT infrastructure (Cisco, VMware, Palo Alto, VDI)
- Python/AI/n8n automation development
- 20,000m2 factory in Turkey (CNC, coil coating)
- Companies in UK, Turkey, UAE, USA
- Construction domain (fire doors, BSA, BIM)

ALREADY KNOWN (avoid repeats):
{chr(10).join(f'- {t}' for t in kwargs.get('known_titles', [])[:15])}

Search for at least 4 different breaking signal queries.

CRITICAL: Your ENTIRE response must be ONLY a valid JSON object. No text before or after.
Format: {{"opportunities": [...], "signals": [...], "cross_pollinations": [...]}}
Include "action_by" date (YYYY-MM-DD or null) for time-sensitive opportunities.

Score each opportunity. Only include founder_fit >= 5."""

        return self._execute_search(prompt, model, max_tokens, max_loops)

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 2: CONTRARIAN SEARCH (Anti-Herd)
    # ═══════════════════════════════════════════════════════════

    def _strategy_contrarian(self, model: str, max_tokens: int,
                              max_loops: int, **kwargs) -> dict:
        """
        Look where nobody else is looking.
        Find neglected sectors adjacent to hot markets.
        """
        rotation = kwargs.get('rotation', {})
        rotation_sectors = rotation.get('sectors', [])
        rotation_name = rotation.get('name', 'diverse sectors')

        prompt = f"""You are the Contrarian Search strategy of OpportunityScout's Serendipity Engine.

MISSION: Find opportunities where competition is LOWEST because everyone's attention is elsewhere.

STEP 1 — THE HERD: Search for "most funded startup sectors 2025 2026" and "hot tech sectors investors". What is EVERYONE piling into?

STEP 2 — THE NEGLECTED: For each hot sector, identify the ADJACENT or SUPPORTING sectors that everyone ignores:
- If everyone builds AI chatbots → who builds AI testing/monitoring/security tools?
- If everyone builds fintech apps → who handles fintech compliance/audit/infrastructure?
- If everyone builds SaaS → who builds SaaS billing/analytics/migration tools?
- If everyone goes direct-to-consumer → who handles B2B wholesale/logistics?

STEP 3 — THE OPPORTUNITY: For each neglected sector, search:
- Is there real buyer demand? (Check: complaints, job postings, spending data)
- How much do buyers currently pay for bad alternatives?
- Could the operator's capabilities serve this gap?

THIS WEEK'S ROTATION FOCUS (prioritize these neglected sectors):
{rotation_name}: {', '.join(rotation_sectors[:5]) if rotation_sectors else 'scan broadly'}

OPERATOR CAPABILITIES:
- 20yr IT infrastructure (Cisco, VMware, Palo Alto, VDI, Veeam)
- Python/AI/n8n automation (Claude API, AWS, Docker, Terraform)
- 20,000m2 factory Turkey (CNC, coil coating, specialty paints)
- Companies in UK, Turkey, UAE, USA (cross-border arbitrage)
- Construction: fire doors, BSA, BIM (but DON'T default to this)

ALREADY KNOWN (avoid repeats):
{chr(10).join(f'- {t}' for t in kwargs.get('known_titles', [])[:15])}

Include "action_by" date (YYYY-MM-DD or null) for time-sensitive opportunities.

Search for at least 5 queries — 2 about hot sectors (to identify the herd), 3+ about adjacent/neglected sectors.
Each opportunity MUST include a "discovery_path" field explaining: hot sector → neglected adjacent → opportunity.
Score each. Only include founder_fit >= 5.

CRITICAL: Your ENTIRE response must be ONLY a valid JSON object. No text before or after.
Format: {{"opportunities": [...], "signals": [...], "cross_pollinations": [...]}}"""

        return self._execute_search(prompt, model, max_tokens, max_loops)

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 3: BUYER JOURNEY MINING
    # ═══════════════════════════════════════════════════════════

    def _strategy_buyer_journey(self, model: str, max_tokens: int,
                                 max_loops: int, **kwargs) -> dict:
        """
        Start from DEMAND, not supply.
        Map a buyer persona's entire spend and find gaps.
        """
        rotation = kwargs.get('rotation', {})
        personas = rotation.get('buyer_personas', [
            "UK SME operations manager",
            "UK property management company",
            "UAE hotel procurement director"
        ])

        # Pick one persona per run (rotate through them)
        day_of_year = datetime.utcnow().timetuple().tm_yday
        persona = personas[day_of_year % len(personas)]

        prompt = f"""You are the Buyer Journey Mining strategy of OpportunityScout's Serendipity Engine.

MISSION: Start from a REAL BUYER and map their complete spending to find gaps.

TARGET BUYER PERSONA: {persona}

STEP 1 — SPEND MAPPING: Search the web for what this buyer type spends money on annually.
- "What do {persona}s spend on annually?"
- "Biggest operational costs for {persona}"
- "Most common vendor categories for {persona}"
Build a complete picture: list every spend category and approximate annual amount.

STEP 2 — PAIN DETECTION: For each major spend category, search for:
- "complaints about [vendor type] from [buyer type]"
- "[service category] problems UK businesses"
- Reddit, Trustpilot, industry forums showing frustration
Identify which categories have the WORST solutions (most complaints, highest prices, worst service).

STEP 3 — GAP ANALYSIS: For each high-pain category:
- What are the current options? (search for "[service] UK providers")
- What do they charge?
- What's missing or broken about them?
- Could the operator offer something better, cheaper, or more specialized?

STEP 4 — OPPORTUNITY DESIGN: For viable gaps, design a specific service/product.

OPERATOR CAPABILITIES:
{self._founder_profile}

ALREADY KNOWN (avoid repeats):
{chr(10).join(f'- {t}' for t in kwargs.get('known_titles', [])[:15])}

Include "action_by" date (YYYY-MM-DD or null) for time-sensitive opportunities.

Search for at least 5 queries mapping this buyer's world.
Each opportunity MUST have "discovery_path" explaining: buyer → spend category → pain → gap → opportunity.
Score each. Only include founder_fit >= 5.

CRITICAL: Your ENTIRE response must be ONLY a valid JSON object. No text before or after.
Format: {{"opportunities": [...], "signals": [...], "cross_pollinations": [...]}}"""

        return self._execute_search(prompt, model, max_tokens, max_loops)

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 4: FRONTIER SCANNER
    # ═══════════════════════════════════════════════════════════

    def _strategy_frontier_scanner(self, model: str, max_tokens: int,
                                    max_loops: int, **kwargs) -> dict:
        """
        Catch unicorn-potential opportunities at the technology frontier.
        Emerging tech × founder skills intersections.
        """
        prompt = f"""You are the Frontier Scanner strategy of OpportunityScout's Serendipity Engine.

MISSION: Find business opportunities at the CUTTING EDGE of technology that match the operator's skills.

STEP 1 — FRONTIER SCAN: Search for technologies that reached COMMERCIAL VIABILITY in the last 6 months:
- "emerging technology commercially available 2025 2026"
- "new AI capabilities business applications"
- "technology cost breakthrough 2025"
- "new APIs and developer tools launched recently"
Focus on: things that just became CHEAP enough to use, EASY enough to deploy, or RELIABLE enough to sell.

STEP 2 — CAPABILITY INTERSECTION: For each frontier technology, check against the operator's 5 capability clusters:

1. IT INFRASTRUCTURE (Cisco, VMware, Palo Alto, VDI, Veeam — 20yr expertise):
   → Can this tech be deployed/managed using IT infrastructure skills?
   → Is there a new monitoring/security/management need?

2. AI/SOFTWARE (Python, n8n, Claude API, AWS, Docker, Terraform):
   → Can this tech be wrapped into a SaaS product?
   → Can n8n automate workflows around this tech?
   → Can Claude API enhance this tech's value?

3. MANUFACTURING (CNC, coil coating, factory operations):
   → Does this tech apply to manufacturing/Industry 4.0?
   → Can factory capacity be used to produce something this tech enables?

4. CROSS-BORDER (UK/TR/UAE/US entities, import/export):
   → Does this tech create cross-border opportunities?
   → Price arbitrage using Turkish operations + new tech?

5. CONSTRUCTION (BSA, fire doors, BIM — limit to 1 result max):
   → Any construction-adjacent application?

STEP 3 — FIRST MOVER ANALYSIS: For promising intersections:
- Who are the FIRST movers? What are they charging?
- What's the gap between first movers and the mass market?
- Can the operator be an early adopter/reseller/integrator?

ALREADY KNOWN (avoid repeats):
{chr(10).join(f'- {t}' for t in kwargs.get('known_titles', [])[:15])}

Include "action_by" date (YYYY-MM-DD or null) for time-sensitive opportunities.

Search for at least 5 frontier technology queries.
Each opportunity MUST have "discovery_path" explaining: frontier tech → capability match → market gap → opportunity.
Score each. Only include founder_fit >= 5. Mark construction max 1.

CRITICAL: Your ENTIRE response must be ONLY a valid JSON object. No text before or after.
Format: {{"opportunities": [...], "signals": [...], "cross_pollinations": [...]}}"""

        return self._execute_search(prompt, model, max_tokens, max_loops)

    # ═══════════════════════════════════════════════════════════
    # SEARCH EXECUTION (shared by all strategies)
    # ═══════════════════════════════════════════════════════════

    def _execute_search(self, prompt: str, model: str,
                        max_tokens: int, max_loops: int) -> dict:
        """Execute a multi-turn web search conversation with Claude."""
        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.llm.create(
                model=model,
                max_tokens=max_tokens,
                system=self._system_prompt,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=messages
            )

            loop_count = 0
            while response.stop_reason == "tool_use" and loop_count < max_loops:
                loop_count += 1
                logger.info(f"   🔍 Search loop {loop_count}")
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Search completed."
                        })

                messages.append({"role": "user", "content": tool_results})

                response = self.llm.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=self._system_prompt,
                    tools=[{"type": "web_search_20250305", "name": "web_search"}],
                    messages=messages
                )

            text = self._extract_text(response)
            results = self._parse_json_response(text)
            filtered = self._filter_by_founder_fit(results)

            return {
                "opportunities": filtered,
                "signals": results.get('signals', []),
                "cross_pollinations": results.get('cross_pollinations', []),
                "search_loops": loop_count
            }

        except Exception as e:
            logger.error(f"Search execution failed: {e}")
            return {"opportunities": [], "signals": [], "cross_pollinations": []}

    # ═══════════════════════════════════════════════════════════
    # SECTOR ROTATION
    # ═══════════════════════════════════════════════════════════

    def _load_sector_rotation(self) -> dict:
        """Load sector rotation config."""
        try:
            with open(SECTOR_ROTATION_PATH) as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}

    def _get_current_rotation(self) -> dict:
        """Get this week's rotation focus."""
        rotation = self._sector_rotation.get('rotation', {})
        day = datetime.utcnow().day
        week_num = min((day - 1) // 7 + 1, 5)  # 1-5
        week_key = f"week_{week_num}"
        return rotation.get(week_key, rotation.get('week_1', {}))

    # ═══════════════════════════════════════════════════════════
    # FILTERING & STORAGE (preserved from v1)
    # ═══════════════════════════════════════════════════════════

    def _filter_by_founder_fit(self, results: dict) -> list:
        """Filter opportunities by Founder Fit score >= threshold."""
        if isinstance(results, list):
            opps = results
        else:
            opps = results.get('opportunities', [])

        filtered = []
        for opp in opps:
            scores = opp.get('scores', {})
            ff = scores.get('founder_fit', {})
            ff_score = ff.get('score', 0) if isinstance(ff, dict) else (
                ff if isinstance(ff, (int, float)) else 0
            )
            if ff_score >= self._min_founder_fit:
                filtered.append(opp)
            else:
                logger.debug(f"  Filtered out (FF={ff_score}): {opp.get('title', '?')}")
        return filtered

    def _store_results(self, opportunities: list, source_type: str) -> list:
        """Store serendipity findings in the knowledge base."""
        stored = []
        for opp in opportunities:
            # ID is assigned by knowledge_base.save_opportunity() — no need to set here
            opp['source'] = source_type
            if 'serendipity' not in opp.get('tags', []):
                opp.setdefault('tags', []).append('serendipity')

            # Always recalculate score and tier
            opp['weighted_total'] = self._calculate_weighted_total(opp.get('scores', {}))
            opp['tier'] = self._determine_tier(opp['weighted_total'])

            if not self.kb.is_duplicate(opp.get('title', ''), source_type,
                                          sector=opp.get('sector', ''), tags=opp.get('tags', [])):
                self.kb.save_opportunity(opp)
                stored.append(opp)

        return stored

    # ═══════════════════════════════════════════════════════════
    # CONTEXT HELPERS
    # ═══════════════════════════════════════════════════════════

    def _get_known_titles(self, limit: int = 50) -> list:
        """Get titles of known opportunities to avoid repetition."""
        opps = self.kb.get_top_opportunities(limit=limit)
        return [o.get('title', '') for o in opps if o.get('title')]

    def _get_known_tags(self, limit: int = 80) -> list:
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
        """Get a summary of accumulated intelligence."""
        parts = []

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
                parts.append("RISING TRENDS:")
                for t in trends:
                    arrow = {"rising": "↑", "stable": "→",
                             "declining": "↓"}.get(t[2], '?')
                    parts.append(f"  {arrow} {t[0]} (×{t[1]})")
        except Exception:
            pass

        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT description FROM evolution_log
                WHERE action_type = 'blind_spot'
                ORDER BY created_at DESC LIMIT 5
            """)
            spots = cursor.fetchall()
            if spots:
                parts.append("\nBLIND SPOTS:")
                for s in spots:
                    parts.append(f"  {s[0]}")
        except Exception:
            pass

        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT sector, COUNT(*) as cnt, AVG(weighted_total) as avg_score
                FROM opportunities
                WHERE sector IS NOT NULL AND sector != ''
                GROUP BY sector ORDER BY cnt DESC LIMIT 10
            """)
            sectors = cursor.fetchall()
            if sectors:
                parts.append("\nSECTOR DISTRIBUTION:")
                for s in sectors:
                    parts.append(f"  {s[0]}: {s[1]} opps, avg {s[2]:.0f}")
        except Exception:
            pass

        return "\n".join(parts) if parts else "No accumulated data yet."

    # ═══════════════════════════════════════════════════════════
    # SCORING & PARSING
    # ═══════════════════════════════════════════════════════════

    def _calculate_weighted_total(self, scores: dict) -> float:
        return calculate_weighted_total(scores, self.config)

    def _determine_tier(self, weighted_total: float) -> str:
        return determine_tier(weighted_total, self.config)

    def _parse_json_response(self, text: str) -> dict:
        """
        Extract JSON from Claude's response with multiple fallback strategies.
        Handles: clean JSON, code-fenced JSON, text-before-JSON, truncated JSON.
        """
        import re
        default = {"opportunities": [], "signals": [], "cross_pollinations": []}

        if not text or not text.strip():
            return default

        # Strategy 1: Direct parse (clean JSON)
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract from ```json ... ``` code fence
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find first '{' that starts a JSON object with "opportunities"
        first_brace = text.find('{')
        if first_brace >= 0:
            json_candidate = text[first_brace:]
            try:
                return json.loads(json_candidate)
            except json.JSONDecodeError:
                pass

            # Strategy 4: Truncated JSON — try to repair by closing brackets
            # Find the last complete opportunity object and close the arrays
            last_good = self._repair_truncated_json(json_candidate)
            if last_good:
                try:
                    return json.loads(last_good)
                except json.JSONDecodeError:
                    pass

        # Strategy 5: Greedy regex — find largest {...} block containing "opportunities"
        json_match = re.search(r'(\{[\s\S]*"opportunities"\s*:\s*\[[\s\S]*)', text)
        if json_match:
            candidate = json_match.group(1)
            repaired = self._repair_truncated_json(candidate)
            if repaired:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass

        logger.warning("Could not parse JSON from serendipity response")
        logger.warning(f"Raw text (first 500): {text[:500]}")
        return default

    @staticmethod
    def _repair_truncated_json(text: str) -> str:
        """
        Attempt to repair truncated JSON by closing open brackets/braces.
        Finds the last complete JSON object in an array and closes everything.
        """
        if not text:
            return ""

        # Find the last successfully closed object ('},')  or ('}]')
        # by scanning for balanced braces
        depth_brace = 0
        depth_bracket = 0
        last_safe_pos = 0

        i = 0
        in_string = False
        escape_next = False

        while i < len(text):
            ch = text[i]

            if escape_next:
                escape_next = False
                i += 1
                continue

            if ch == '\\' and in_string:
                escape_next = True
                i += 1
                continue

            if ch == '"' and not escape_next:
                in_string = not in_string
                i += 1
                continue

            if in_string:
                i += 1
                continue

            if ch == '{':
                depth_brace += 1
            elif ch == '}':
                depth_brace -= 1
                if depth_brace >= 0:
                    last_safe_pos = i + 1
            elif ch == '[':
                depth_bracket += 1
            elif ch == ']':
                depth_bracket -= 1

            i += 1

        # If already balanced, return as-is
        if depth_brace == 0 and depth_bracket == 0:
            return text

        # Truncate to last safe position and close remaining brackets
        repaired = text[:last_safe_pos]

        # Close any remaining open brackets/arrays
        # Count current depth at last_safe_pos
        depth_brace = 0
        depth_bracket = 0
        in_string = False
        escape_next = False

        for ch in repaired:
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth_brace += 1
            elif ch == '}':
                depth_brace -= 1
            elif ch == '[':
                depth_bracket += 1
            elif ch == ']':
                depth_bracket -= 1

        # Append closing brackets
        repaired += ']' * depth_bracket + '}' * depth_brace

        return repaired

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
