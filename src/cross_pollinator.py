"""
OpportunityScout — Cross-Pollinator Module

Actively seeks connections between opportunities from DIFFERENT sectors.
Instead of passively storing cross-pollinations, this module:
1. Pulls recent opportunities across ALL sectors
2. Uses Claude Opus to find non-obvious connections
3. For each connection, generates hybrid opportunity search queries
4. Executes those searches
5. Tracks which cross-pollinations led to actual discoveries

Types of connections sought:
- Same buyer, different need (bundle opportunity)
- Same technology, different application
- Same regulatory driver across sectors
- Supply chain connections
- Geographic arbitrage spanning sectors
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime

logger = logging.getLogger("scout.crosspoll")

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


class CrossPollinator:
    """
    Active cross-sector connection engine.
    Finds non-obvious links between opportunities and generates hybrid ideas.
    """

    def __init__(self, config: dict, knowledge_base, event_bus=None):
        self.config = config
        self.kb = knowledge_base
        self.event_bus = event_bus

        claude_config = config.get('claude', {})
        self.api_key = claude_config.get('api_key') or os.environ.get('ANTHROPIC_API_KEY', '')
        self.model_opus = claude_config.get('model_deep_dive', 'claude-opus-4-20250514')
        self.model_sonnet = claude_config.get('model', 'claude-sonnet-4-20250514')

        if HAS_ANTHROPIC and self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
        else:
            self.client = None

    def run_cross_pollination(self) -> dict:
        """
        Main entry point. Runs the full cross-pollination cycle:
        1. Gather diverse opportunities
        2. Find connections with Opus
        3. Search for hybrid opportunities
        4. Score and store results
        """
        if not self.client:
            logger.error("Anthropic client not available for cross-pollination")
            return {'connections': [], 'hybrid_opportunities': []}

        logger.info("🔗 Starting cross-pollination cycle...")
        start_time = time.time()

        # Step 1: Gather recent opportunities from diverse sectors
        opportunities = self._gather_diverse_opportunities()
        if len(opportunities) < 3:
            logger.warning("Not enough diverse opportunities for cross-pollination")
            return {'connections': [], 'hybrid_opportunities': [], 'reason': 'insufficient_data'}

        # Step 2: Find connections with Opus
        connections = self._find_connections(opportunities)

        # Step 3: For each connection, search for hybrid opportunities
        hybrid_opportunities = []
        for conn in connections[:5]:  # Max 5 to control cost
            hybrids = self._search_hybrid(conn)
            hybrid_opportunities.extend(hybrids)

            # Publish to event bus
            if self.event_bus:
                self.event_bus.publish('cross_pollination', {
                    'connection_type': conn.get('connection_type', 'unknown'),
                    'sectors_connected': conn.get('sectors', []),
                    'hybrid_idea': conn.get('hybrid_opportunity', ''),
                    'hybrids_found': len(hybrids)
                }, source_module='cross_pollinator')

        # Store cross-pollinations in KB
        for conn in connections:
            self.kb.save_cross_pollination(
                insight=conn.get('insight', ''),
                opp_ids=conn.get('opportunity_ids', []),
                novel_angle=conn.get('hybrid_opportunity', '')
            )

        duration = time.time() - start_time

        # Log strategy performance
        try:
            self.kb.log_strategy_performance(
                engine='cross_pollinator',
                strategy_name='cross_pollination',
                opportunities_found=len(hybrid_opportunities),
                avg_score=self._avg_score(hybrid_opportunities),
                best_score=self._max_score(hybrid_opportunities),
                fire_count=sum(1 for o in hybrid_opportunities if o.get('tier') == 'FIRE'),
                high_count=sum(1 for o in hybrid_opportunities if o.get('tier') == 'HIGH'),
                cost_usd=0.08 * len(connections),  # Approximate
                duration_seconds=duration
            )
        except Exception:
            pass

        logger.info(
            f"🔗 Cross-pollination: {len(connections)} connections, "
            f"{len(hybrid_opportunities)} hybrid opportunities ({duration:.0f}s)"
        )

        return {
            'connections': connections,
            'hybrid_opportunities': hybrid_opportunities,
            'duration': duration
        }

    def _gather_diverse_opportunities(self) -> list:
        """Gather recent opportunities ensuring sector diversity."""
        try:
            recent = self.kb.get_recent_opportunities(hours=720)  # 30 days
        except Exception:
            return []

        if not recent:
            return []

        # Group by sector
        by_sector = {}
        for opp in recent:
            sector = opp.get('sector', 'Unknown')
            if sector not in by_sector:
                by_sector[sector] = []
            by_sector[sector].append(opp)

        # Pick top 2-3 from each sector (max 15 total)
        diverse = []
        for sector, opps in by_sector.items():
            # Sort by score, take top 2-3
            sorted_opps = sorted(opps, key=lambda x: x.get('weighted_total', 0), reverse=True)
            diverse.extend(sorted_opps[:3])

        # Limit total
        return diverse[:15]

    def _find_connections(self, opportunities: list) -> list:
        """Use Opus to find non-obvious connections between opportunities."""
        # Build opportunity summary for the prompt
        opp_summaries = []
        for i, opp in enumerate(opportunities, 1):
            opp_summaries.append(
                f"{i}. [{opp.get('sector', '?')}] {opp.get('title', '?')} "
                f"(Score: {opp.get('weighted_total', 0)}) — {opp.get('one_liner', '')}"
            )

        opp_text = '\n'.join(opp_summaries)

        prompt = (
            f"You are a cross-sector innovation analyst. Your job is to find "
            f"NON-OBVIOUS connections between opportunities from DIFFERENT sectors.\n\n"
            f"OPPORTUNITIES (from various sectors):\n{opp_text}\n\n"
            f"Find 3-5 connections between opportunities from DIFFERENT sectors. "
            f"For each connection:\n\n"
            f"1. SAME BUYER, DIFFERENT NEED — Is there a buyer who needs multiple "
            f"of these services? Bundle opportunity.\n"
            f"2. SAME TECHNOLOGY, DIFFERENT APPLICATION — Can the tech from one sector "
            f"solve a problem in another?\n"
            f"3. SAME REGULATORY DRIVER — Does one regulation create opportunities "
            f"across multiple sectors?\n"
            f"4. SUPPLY CHAIN CONNECTION — Does one opportunity feed into another?\n"
            f"5. GEOGRAPHIC ARBITRAGE — Can cross-border expertise connect two opportunities?\n\n"
            f"For each connection, design a SPECIFIC hybrid business opportunity.\n\n"
            f"Return JSON array:\n"
            f'[{{"connection_type": "same_buyer|same_tech|regulatory|supply_chain|arbitrage", '
            f'"sectors": ["sector1", "sector2"], '
            f'"opportunity_ids": ["OPP-...", "OPP-..."], '
            f'"insight": "Why these connect (1-2 sentences)", '
            f'"hybrid_opportunity": "Specific business idea combining both (2-3 sentences)", '
            f'"search_query": "Web search query to validate this hybrid idea"}}]'
        )

        try:
            result = self._call_claude(prompt, model=self.model_opus, max_tokens=4096)
            if isinstance(result, list):
                return result
            return []
        except Exception as e:
            logger.error(f"Failed to find connections: {e}")
            return []

    def _search_hybrid(self, connection: dict) -> list:
        """Search for evidence of a hybrid opportunity."""
        query = connection.get('search_query', '')
        if not query:
            return []

        conn_type = connection.get("connection_type", "")
        hybrid_idea = connection.get('hybrid_opportunity', '')
        json_tmpl = (
            '{"title": "...", "one_liner": "...", "sector": "...", '
            '"why_now": "...", "first_move": "...", '
            '"revenue_path": "...", "risks": ["..."], '
            '"discovery_path": "cross-pollination: ' + conn_type + '", '
            '"tags": ["cross-pollination", "..."], '
            '"scores": {"founder_fit": {"score": N, "reason": "..."}, ...}}'
        )
        no_viable_tmpl = '{"viable": false, "reason": "..."}'

        prompt = (
            f"Search the web for this specific business opportunity:\n\n"
            f"IDEA: {hybrid_idea}\n"
            f"SEARCH: {query}\n\n"
            f"Find evidence that this idea could work:\n"
            f"- Are there companies doing something similar?\n"
            f"- What is the market size?\n"
            f"- What would customers pay?\n"
            f"- What are the barriers?\n\n"
            f"If you find a viable opportunity, return it as JSON:\n"
            f"{json_tmpl}\n\n"
            f"If no viable opportunity, return: {no_viable_tmpl}"
        )

        try:
            result = self._call_claude(prompt, model=self.model_sonnet, max_tokens=4096)
            if isinstance(result, dict):
                if result.get('viable') is False:
                    return []
                if result.get('title'):
                    # Add ID and metadata
                    # ID is assigned by knowledge_base.save_opportunity()
                    result['source'] = 'cross_pollinator'
                    result['discovery_strategy'] = 'cross_pollination'
                    return [result]
            return []
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []

    def _call_claude(self, prompt: str, model: str = None, max_tokens: int = 4096):
        """Execute Claude API call with web search, return parsed result."""
        if not self.client:
            return None

        model = model or self.model_sonnet
        messages = [{"role": "user", "content": prompt}]

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                tools=[{"type": "web_search_20250305"}],
                messages=messages
            )

            # Handle multi-turn
            max_loops = 15
            loop = 0
            while response.stop_reason == "tool_use" and loop < max_loops:
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Search completed."
                        })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    tools=[{"type": "web_search_20250305"}],
                    messages=messages
                )
                loop += 1

            # Extract text
            text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text += block.text

            if text:
                return self._extract_json(text)
            return None

        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            return None

    @staticmethod
    def _extract_json(text: str):
        """Extract JSON from text (array or object)."""
        import re
        # Try to find JSON block
        for pattern in [r'\[[\s\S]*\]', r'\{[\s\S]*\}']:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    continue
        return None

    @staticmethod
    def _avg_score(opportunities: list) -> float:
        if not opportunities:
            return 0
        scores = [o.get('weighted_total', 0) for o in opportunities]
        return round(sum(scores) / len(scores), 1) if scores else 0

    @staticmethod
    def _max_score(opportunities: list) -> float:
        if not opportunities:
            return 0
        return max((o.get('weighted_total', 0) for o in opportunities), default=0)
