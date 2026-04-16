"""
OpportunityScout — Competitive Monitor

Tracks competitors for FIRE/HIGH opportunities.
For each top opportunity, identifies companies in adjacent space,
monitors their activity, and detects openings.

Features:
- Auto-identifies competitors for FIRE/HIGH opportunities
- Monthly web search for funding rounds, launches, pivots
- Publishes competitor_detected / competitor_weakness events
- CLI/Telegram accessible
"""

import json
import logging
import time
import uuid
from datetime import datetime

logger = logging.getLogger("scout.competitors")

from .llm_router import LLMRouter


class CompetitiveMonitor:
    """
    Monitors competitive landscape for top opportunities.
    """

    def __init__(self, config: dict, knowledge_base, event_bus=None):
        self.config = config
        self.kb = knowledge_base
        self.event_bus = event_bus

        self.llm = LLMRouter(config)
        self.model = self.llm.get_model('daily')

    def identify_competitors(self, opportunity: dict) -> list:
        """
        For a given opportunity, identify 3-5 companies in adjacent space.
        Uses Claude + web search to find real competitors.
        """
        if not self.llm:
            logger.error("LLM router not available")
            return []

        title = opportunity.get('title', '')
        one_liner = opportunity.get('one_liner', '')
        sector = opportunity.get('sector', '')

        prompt = (
            f"You are a competitive intelligence analyst.\n\n"
            f"OPPORTUNITY: {title}\n"
            f"Description: {one_liner}\n"
            f"Sector: {sector}\n\n"
            f"Find 3-5 real companies that are competitors or adjacent players "
            f"in this market space. For each company provide:\n"
            f"1. Company name\n"
            f"2. What they do (1 sentence)\n"
            f"3. Funding raised (if known)\n"
            f"4. Strengths\n"
            f"5. Weaknesses / gaps we could exploit\n\n"
            f"Search the web for real, current information. Do NOT make up companies.\n\n"
            f"Return JSON array:\n"
            f'[{{"company": "...", "description": "...", "funding": "...", '
            f'"strengths": "...", "weaknesses": "...", "url": "..."}}]'
        )

        try:
            competitors = self._execute_search(prompt)
            return competitors
        except Exception as e:
            logger.error(f"Failed to identify competitors: {e}")
            return []

    def monitor_tracked(self) -> list:
        """
        Check all tracked competitors for updates.
        Returns list of intelligence updates.
        """
        if not self.llm:
            logger.error("LLM router not available")
            return []

        try:
            tracked = self.kb.get_tracked_competitors()
        except Exception:
            return []

        updates = []

        for comp in tracked:
            company = comp.get('company_name', '')
            sector = comp.get('sector', '')

            prompt = (
                f"You are a competitive intelligence analyst. "
                f"Search for the latest news about {company} "
                f"(sector: {sector}).\n\n"
                f"Look for:\n"
                f"1. New funding rounds or acquisitions\n"
                f"2. Product launches or pivots\n"
                f"3. Layoffs, shutdowns, or struggles\n"
                f"4. Customer complaints or market shifts\n\n"
                f"If you find significant news, summarize it. "
                f"If nothing notable, say 'No significant updates.'\n\n"
                f"Return JSON:\n"
                f'{{"company": "{company}", "status": "active|struggling|growing|pivoting|shutdown", '
                f'"latest_intel": "...", "opportunity_signal": true/false, '
                f'"signal_description": "..."}}'
            )

            try:
                result = self._execute_search(prompt)
                if result:
                    intel = result if isinstance(result, dict) else result[0] if isinstance(result, list) else None
                    if intel:
                        # Update KB
                        self.kb.save_competitor(
                            company_name=company,
                            sector=sector,
                            related_opp_ids=comp.get('related_opportunity_ids', []),
                            intel=intel.get('latest_intel', '')
                        )

                        # Publish events for significant changes
                        if intel.get('opportunity_signal'):
                            if self.event_bus:
                                event_type = (
                                    'competitor_weakness'
                                    if intel.get('status') in ('struggling', 'shutdown', 'pivoting')
                                    else 'competitor_detected'
                                )
                                self.event_bus.publish(event_type, {
                                    'company': company,
                                    'sector': sector,
                                    'status': intel.get('status'),
                                    'intel': intel.get('signal_description', ''),
                                }, source_module='competitive_monitor')

                        updates.append(intel)
            except Exception as e:
                logger.error(f"Failed to monitor {company}: {e}")

        return updates

    def scan_for_opportunity(self, opportunity_id: str = None) -> dict:
        """
        Full competitive scan: identify competitors for FIRE/HIGH opportunities
        that don't have competitors tracked yet, then monitor existing ones.
        """
        results = {
            'new_competitors_identified': 0,
            'competitors_monitored': 0,
            'signals_found': 0,
            'updates': []
        }

        # Step 1: Find FIRE/HIGH opportunities without tracked competitors
        try:
            if opportunity_id:
                opp = self.kb.get_opportunity(opportunity_id)
                top_opps = [opp] if opp else []
            else:
                top_opps = self.kb.get_top_opportunities(limit=10)
                top_opps = [o for o in top_opps if o.get('tier') in ('FIRE', 'HIGH')]
        except Exception:
            top_opps = []

        for opp in top_opps[:5]:  # Max 5 to control cost
            opp_id = opp.get('id', '')
            # Check if already has competitors tracked
            try:
                existing = self.kb.get_tracked_competitors()
                has_competitors = any(
                    opp_id in c.get('related_opportunity_ids', '')
                    for c in existing
                )
            except Exception:
                has_competitors = False

            if not has_competitors:
                competitors = self.identify_competitors(opp)
                for comp in competitors:
                    self.kb.save_competitor(
                        company_name=comp.get('company', ''),
                        sector=opp.get('sector', ''),
                        related_opp_ids=[opp_id],
                        intel=comp.get('description', '')
                    )
                    results['new_competitors_identified'] += 1

        # Step 2: Monitor all tracked competitors
        updates = self.monitor_tracked()
        results['competitors_monitored'] = len(updates)
        results['signals_found'] = sum(
            1 for u in updates if u.get('opportunity_signal')
        )
        results['updates'] = updates

        logger.info(
            f"🏢 Competitive scan: {results['new_competitors_identified']} new, "
            f"{results['competitors_monitored']} monitored, "
            f"{results['signals_found']} signals"
        )

        return results

    def get_competitor_report(self) -> str:
        """Generate formatted competitor report."""
        try:
            tracked = self.kb.get_tracked_competitors()
        except Exception:
            return "No competitor data available."

        if not tracked:
            return "No competitors being tracked. Run a competitive scan first."

        lines = ["🏢 COMPETITIVE INTELLIGENCE REPORT\n"]
        lines.append("=" * 40)

        for comp in tracked:
            status_emoji = {
                'active': '🟢', 'growing': '📈', 'struggling': '🔴',
                'pivoting': '🔄', 'shutdown': '💀'
            }.get(comp.get('status', 'active'), '⚪')

            lines.append(
                f"\n{status_emoji} {comp.get('company_name', '?')}\n"
                f"   Sector: {comp.get('sector', 'N/A')}\n"
                f"   Status: {comp.get('status', 'active')}\n"
                f"   Intel: {comp.get('latest_intel', 'N/A')[:150]}\n"
                f"   Last checked: {comp.get('last_checked', 'never')}"
            )

        return '\n'.join(lines)

    def _execute_search(self, prompt: str):
        """Execute a Claude API call with web search tool."""
        if not self.llm:
            return None

        messages = [{"role": "user", "content": prompt}]

        try:
            response = self.llm.create(
                model=self.model,
                max_tokens=4096,
                tools=[{"type": "web_search_20250305"}],
                messages=messages
            )

            # Handle multi-turn web search
            max_loops = 10
            loop = 0
            while response.stop_reason == "tool_use" and loop < max_loops:
                # Build assistant + tool result messages
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

                response = self.llm.create(
                    model=self.model,
                    max_tokens=4096,
                    tools=[{"type": "web_search_20250305"}],
                    messages=messages
                )
                loop += 1

            # Extract text content
            text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text += block.text

            # Parse JSON from response
            if text:
                # Try to find JSON in the response
                json_match = self._extract_json(text)
                if json_match is not None:
                    return json_match

            return None

        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            return None

    @staticmethod
    def _extract_json(text: str):
        """Extract JSON array or object from text."""
        import re
        # Try array first
        match = re.search(r'\[[\s\S]*?\]', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        # Try object
        match = re.search(r'\{[\s\S]*?\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None
