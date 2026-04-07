"""
OpportunityScout — Capability Explorer

The game-changer module. Inverts discovery direction: starts from each
founder capability cluster, systematically explores adjacent industries.

Instead of asking "what opportunities exist?" it asks:
"What industries need Cisco expertise? What can a coil coating factory
produce besides furniture? Where do n8n skills create value?"

Exploration weights prevent construction bias structurally:
- IT Infrastructure: 2.0 (most underexploited)
- AI/Software: 1.5
- Cross-border: 1.5
- Manufacturing: 1.0
- Construction: 0.5 (already over-explored)
"""

import json
import logging
import os
import time
import uuid
import yaml
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic
from src.scoring_utils import calculate_weighted_total, determine_tier

logger = logging.getLogger("scout.capability_explorer")

CAPABILITY_MAP_PATH = Path("./config/capability_map.yaml")
FOUNDER_PROFILE_PATH = Path("./config/founder_profile.yaml")
SYSTEM_PROMPT_PATH = Path("./SYSTEM_PROMPT.md")


class CapabilityExplorer:
    """
    Capability-first discovery engine.
    Explores what industries NEED the founder's specific skills.
    """

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.client = Anthropic(
            api_key=config.get('claude', {}).get('api_key')
            or os.environ.get('ANTHROPIC_API_KEY')
        )
        self.model = config.get('claude', {}).get(
            'model', 'claude-sonnet-4-20250514'
        )
        self._system_prompt = self._load_file(SYSTEM_PROMPT_PATH)
        self._founder_profile = self._load_file(FOUNDER_PROFILE_PATH)
        self._capability_map = self._load_capability_map()

    # ═══════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════

    def explore(self, capability: str = None, industry: str = None) -> dict:
        """
        Run a capability exploration cycle.

        If capability/industry specified: explore that specific intersection.
        If not: auto-select the LEAST explored capability cluster and industry.

        Returns:
            dict with exploration results, opportunities found, negative evidence.
        """
        # Auto-select if not specified
        if not capability:
            capability = self._select_least_explored_capability()
        if not industry:
            industry = self._select_least_explored_industry(capability)

        if not capability or not industry:
            logger.warning("🔭 No capability/industry to explore")
            return {"capability": capability, "industry": industry,
                    "opportunities": [], "negative_evidence": None}

        logger.info(f"🔭 Exploring: {capability} × {industry}")
        start_time = time.time()

        # Get capability details from map
        cap_data = self._capability_map.get('capabilities', {}).get(capability, {})
        core_skills = cap_data.get('core_skills', [])
        industry_data = cap_data.get('adjacent_industries', {}).get(industry, {})
        industry_desc = industry_data.get('description', industry) if isinstance(industry_data, dict) else industry

        # Build and execute the exploration prompt
        prompt = self._build_exploration_prompt(
            capability, core_skills, industry, industry_desc
        )

        try:
            result = self._execute_search(prompt)
            opportunities = result.get('opportunities', [])
            negative_evidence = None

            if not opportunities:
                # No opportunities found = negative evidence (valuable signal!)
                negative_evidence = (
                    f"Explored {capability} × {industry}: no viable opportunities found. "
                    f"This may indicate: market too small, skills don't transfer, "
                    f"or existing players have strong moats."
                )
                logger.info(f"🔭 Negative evidence: {capability} × {industry} — no opportunities")

                # Publish negative_evidence event if event bus available
                try:
                    from src.event_bus import EventBus
                    # Event bus will be accessed through scout_engine
                except ImportError:
                    pass

            # Store opportunities
            stored = self._store_results(opportunities, capability, industry)

            duration = time.time() - start_time

            # Log exploration
            scores = [o.get('weighted_total', 0) for o in stored]
            self.kb.save_exploration(
                capability=capability,
                industry=industry,
                opportunities_found=len(stored),
                negative_evidence=negative_evidence,
                best_score=max(scores) if scores else 0,
                notes=f"Found {len(stored)} opps in {duration:.0f}s"
            )

            # Log strategy performance
            fire_count = len([o for o in stored if o.get('tier') == 'FIRE'])
            high_count = len([o for o in stored if o.get('tier') == 'HIGH'])

            self.kb.log_strategy_performance(
                engine='capability_explorer',
                strategy_name=f"{capability}__{industry}",
                opportunities_found=len(stored),
                avg_score=round(sum(scores) / len(scores), 1) if scores else 0,
                best_score=max(scores) if scores else 0,
                fire_count=fire_count,
                high_count=high_count,
                duration_seconds=round(duration, 1)
            )

            # Mark industry as explored in capability map
            self._mark_explored(capability, industry)

            logger.info(
                f"🔭 Exploration complete: {capability} × {industry} → "
                f"{len(stored)} opps (🔥{fire_count} ⭐{high_count}) in {duration:.0f}s"
            )

            return {
                "capability": capability,
                "industry": industry,
                "industry_description": industry_desc,
                "opportunities": stored,
                "negative_evidence": negative_evidence,
                "fire_count": fire_count,
                "high_count": high_count,
                "duration": round(duration, 1)
            }

        except Exception as e:
            logger.error(f"🔭 Exploration failed: {capability} × {industry}: {e}")
            return {
                "capability": capability,
                "industry": industry,
                "opportunities": [],
                "error": str(e)
            }

    def explore_multiple(self, count: int = 5) -> dict:
        """Run multiple exploration cycles, rotating through capabilities."""
        logger.info(f"🔭 Running {count} capability explorations...")

        all_results = []
        for i in range(count):
            result = self.explore()
            all_results.append(result)

        total_opps = sum(len(r.get('opportunities', [])) for r in all_results)
        total_fire = sum(r.get('fire_count', 0) for r in all_results)

        logger.info(f"🔭 {count} explorations complete: {total_opps} total opps, 🔥{total_fire}")

        return {
            "explorations": all_results,
            "total_opportunities": total_opps,
            "total_fire": total_fire
        }

    def expand_adjacency_map(self) -> dict:
        """Ask Claude to suggest NEW adjacent industries for each capability."""
        logger.info("🔭 Expanding capability adjacency map...")

        current_map = yaml.dump(self._capability_map, default_flow_style=False)

        prompt = f"""Analyze this capability-to-industry adjacency map and suggest NEW industries to explore for each capability cluster.

CURRENT MAP:
{current_map}

EXPLORATION HISTORY (what's been explored):
{self._get_exploration_summary()}

For each capability cluster, suggest 3-5 NEW adjacent industries that are NOT already in the map. Focus on:
1. Industries with high growth potential
2. Industries where the specific skills create a real competitive advantage
3. Non-obvious cross-industry applications
4. Industries where few competitors have this specific skillset

Return as JSON:
```json
{{
  "suggestions": {{
    "it_infrastructure": [
      {{"name": "industry_key", "description": "Why this industry needs these skills"}}
    ],
    "ai_software": [...],
    "cross_border": [...],
    "manufacturing": [...],
    "construction": [...]
  }}
}}
```"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": prompt}]
            )

            text = self._extract_text(response)
            return self._parse_json(text)

        except Exception as e:
            logger.error(f"Map expansion failed: {e}")
            return {"suggestions": {}}

    # ═══════════════════════════════════════════════════════════
    # SELECTION LOGIC
    # ═══════════════════════════════════════════════════════════

    def _select_least_explored_capability(self) -> str:
        """Pick the capability cluster with least explorations, weighted."""
        capabilities = self._capability_map.get('capabilities', {})
        if not capabilities:
            return 'it_infrastructure'

        # Count explorations per capability
        exploration_counts = {}
        for cap_name in capabilities:
            history = self.kb.get_exploration_history(capability=cap_name, limit=100)
            weight = capabilities[cap_name].get('weight', 1.0)
            # Effective count = actual count / weight (higher weight = lower effective count)
            exploration_counts[cap_name] = len(history) / weight

        # Return least explored
        return min(exploration_counts, key=exploration_counts.get)

    def _select_least_explored_industry(self, capability: str) -> str:
        """Pick the least explored adjacent industry for a capability."""
        cap_data = self._capability_map.get('capabilities', {}).get(capability, {})
        industries = cap_data.get('adjacent_industries', {})

        if not industries:
            return None

        # Check which are unexplored
        history = self.kb.get_exploration_history(capability=capability, limit=200)
        explored_industries = set()
        for h in history:
            explored_industries.add(h.get('industry', ''))

        # Prefer unexplored
        unexplored = [i for i in industries if i not in explored_industries]
        if unexplored:
            return unexplored[0]

        # All explored — pick oldest explored
        if explored_industries:
            # Return the one explored longest ago
            return list(industries.keys())[0]

        return list(industries.keys())[0] if industries else None

    # ═══════════════════════════════════════════════════════════
    # PROMPT BUILDING
    # ═══════════════════════════════════════════════════════════

    def _build_exploration_prompt(self, capability: str, core_skills: list,
                                   industry: str, industry_desc: str) -> str:
        """Build the capability × industry exploration prompt."""
        skills_text = "\n".join(f"  - {s}" for s in core_skills)

        return f"""You are the Capability Explorer of OpportunityScout. Your mission is to find business opportunities at the intersection of a SPECIFIC capability and a SPECIFIC industry.

CAPABILITY CLUSTER: {capability}
CORE SKILLS:
{skills_text}

TARGET INDUSTRY: {industry}
DESCRIPTION: {industry_desc}

YOUR RESEARCH PROCESS:

1. MARKET MAPPING: Search the web for:
   - "What services/products exist in {industry}?"
   - "{industry} market size UK 2025"
   - "{industry} service providers UK"
   - "problems in {industry} that {capability} could solve"

2. PAIN POINT DISCOVERY:
   - What are the biggest complaints from buyers in this industry?
   - What's overpriced? What's underserved? What's broken?
   - Are there regulatory changes creating new demand?

3. CAPABILITY MATCH:
   - Could someone with [{', '.join(core_skills[:5])}] offer something better?
   - What SPECIFIC service or product would this look like?
   - What would it cost to deliver? What would buyers pay?

4. COMPETITOR ANALYSIS:
   - Who currently serves this industry? Are they good?
   - What gaps do they leave? What's missing?
   - Could cross-border (Turkish cost advantage) help?

5. OPPORTUNITY DESIGN:
   For each viable opportunity found, design a specific business model.

OPERATOR FULL PROFILE:
{self._founder_profile}

Include "action_by" date (YYYY-MM-DD or null) for time-sensitive opportunities.

If you find NO viable opportunities, say so explicitly and explain why. This is VALUABLE DATA — it tells us where NOT to look.

Search the web for at least 5 targeted queries about this specific industry.

Return in standard JSON format:
```json
{{
  "opportunities": [
    {{
      "id": "OPP-{{YYYYMMDD}}-{{N}}",
      "title": "Specific opportunity title",
      "one_liner": "One sentence",
      "source": "capability_explorer",
      "sector": "{industry}",
      "geography": "UK|Global",
      "scores": {{
        "founder_fit": {{"score": N, "reason": "..."}},
        "ai_unlock": {{"score": N, "reason": "..."}},
        "time_to_revenue": {{"score": N, "reason": "..."}},
        "capital_efficiency": {{"score": N, "reason": "..."}},
        "market_timing": {{"score": N, "reason": "..."}},
        "defensibility": {{"score": N, "reason": "..."}},
        "scale_potential": {{"score": N, "reason": "..."}},
        "geographic_leverage": {{"score": N, "reason": "..."}},
        "competition_gap": {{"score": N, "reason": "..."}},
        "simplicity": {{"score": N, "reason": "..."}}
      }},
      "why_now": "Timing reason",
      "first_move": "Action in next 48 hours",
      "revenue_path": "How this makes money",
      "risks": ["risk1", "risk2"],
      "tags": ["capability-explorer", "{capability}", "{industry}"],
      "discovery_path": "How we found this: {capability} × {industry} → ..."
    }}
  ],
  "signals": [],
  "negative_evidence": null
}}
```

If no opportunities found, return:
```json
{{
  "opportunities": [],
  "signals": [],
  "negative_evidence": "Explanation of why no opportunities exist at this intersection"
}}
```"""

    # ═══════════════════════════════════════════════════════════
    # EXECUTION & STORAGE
    # ═══════════════════════════════════════════════════════════

    def _execute_search(self, prompt: str) -> dict:
        """Execute multi-turn web search."""
        messages = [{"role": "user", "content": prompt}]
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=self._system_prompt,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages
        )

        loop_count = 0
        while response.stop_reason == "tool_use" and loop_count < 15:
            loop_count += 1
            logger.info(f"   🔭 Search loop {loop_count}")
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
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self._system_prompt,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=messages
            )

        text = self._extract_text(response)
        return self._parse_json(text)

    def _store_results(self, opportunities: list, capability: str,
                       industry: str) -> list:
        """Store exploration results."""
        stored = []
        for opp in opportunities:
            # ID is assigned by knowledge_base.save_opportunity() — no need to set here

            opp['source'] = f"capability_explorer_{capability}"
            opp.setdefault('tags', []).extend([
                'capability-explorer', capability, industry
            ])

            # Calculate score
            opp['weighted_total'] = calculate_weighted_total(
                opp.get('scores', {}), self.config
            )
            opp['tier'] = determine_tier(opp['weighted_total'], self.config)

            if not self.kb.is_duplicate(opp.get('title', ''), 'capability_explorer',
                                          sector=opp.get('sector', ''), tags=opp.get('tags', [])):
                self.kb.save_opportunity(opp)
                stored.append(opp)

        return stored

    def _mark_explored(self, capability: str, industry: str):
        """Mark an industry as explored in the capability map."""
        try:
            cap = self._capability_map.get('capabilities', {}).get(capability, {})
            industries = cap.get('adjacent_industries', {})
            if industry in industries:
                ind_data = industries[industry]
                if isinstance(ind_data, dict):
                    ind_data['explored'] = True
                    ind_data['last_explored'] = datetime.utcnow().isoformat()
            # Note: We don't write back to YAML — the KB exploration history
            # is the source of truth. The YAML map is the seed data.
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _get_exploration_summary(self) -> str:
        """Get a text summary of all explorations done so far."""
        history = self.kb.get_exploration_history(limit=100)
        if not history:
            return "No explorations done yet."

        lines = []
        for h in history:
            neg = " (NEGATIVE)" if h.get('negative_evidence') else ""
            lines.append(
                f"  {h['capability']} × {h['industry']}: "
                f"{h['opportunities_found']} opps, best={h['best_score']}{neg}"
            )
        return "\n".join(lines)

    def _load_capability_map(self) -> dict:
        try:
            with open(CAPABILITY_MAP_PATH) as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("capability_map.yaml not found")
            return {}

    def _parse_json(self, text: str) -> dict:
        """Extract JSON with multiple fallback strategies including truncation repair."""
        import re
        default = {"opportunities": [], "signals": [], "negative_evidence": None}

        if not text or not text.strip():
            return default

        # Strategy 1: Direct parse
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Strategy 2: Code fence
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find first '{' and parse from there
        first_brace = text.find('{')
        if first_brace >= 0:
            json_candidate = text[first_brace:]
            try:
                return json.loads(json_candidate)
            except json.JSONDecodeError:
                pass

            # Strategy 4: Repair truncated JSON
            repaired = self._repair_truncated_json(json_candidate)
            if repaired:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass

        logger.warning("Could not parse JSON from exploration response")
        logger.warning(f"Raw text (first 500): {text[:500]}")
        return default

    @staticmethod
    def _repair_truncated_json(text: str) -> str:
        """Repair truncated JSON by closing open brackets/braces."""
        if not text:
            return ""
        depth_brace = 0
        depth_bracket = 0
        last_safe_pos = 0
        in_string = False
        escape_next = False

        for i, ch in enumerate(text):
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
                if depth_brace >= 0:
                    last_safe_pos = i + 1
            elif ch == '[':
                depth_bracket += 1
            elif ch == ']':
                depth_bracket -= 1

        if depth_brace == 0 and depth_bracket == 0:
            return text

        repaired = text[:last_safe_pos]
        # Recount depth at last_safe_pos
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
