"""
OpportunityScout — Opportunity Scorer

Takes raw content items from the web scanner, sends them to Claude API
for analysis and scoring, and returns structured opportunity data.
This is the analytical brain that converts noise into signal.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic

logger = logging.getLogger("scout.scorer")

# Load system prompt from file
SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "SYSTEM_PROMPT.md"


class OpportunityScorer:
    """
    Uses Claude API to analyze content and extract scored opportunities.
    """

    def __init__(self, config: dict):
        self.config = config
        self.client = Anthropic(
            api_key=config.get('claude', {}).get('api_key') or os.environ.get('ANTHROPIC_API_KEY')
        )
        self.model = config.get('claude', {}).get('model', 'claude-sonnet-4-20250514')
        self.model_deep = config.get('claude', {}).get('model_deep_dive', 'claude-opus-4-20250514')
        self.max_tokens = config.get('claude', {}).get('max_tokens', 4096)
        self.max_tokens_deep = config.get('claude', {}).get('max_tokens_deep_dive', 8192)
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load the analysis system prompt from disk."""
        try:
            return SYSTEM_PROMPT_PATH.read_text(encoding='utf-8')
        except FileNotFoundError:
            logger.warning("System prompt file not found, using embedded default")
            return self._default_system_prompt()

    def analyze_batch(self, content_items: list, batch_size: int = 5) -> dict:
        """
        Analyze a batch of content items and extract opportunities.
        Groups items to minimize API calls while staying within context limits.
        
        Returns: {
            "opportunities": [...],
            "signals": [...],
            "cross_pollinations": [...]
        }
        """
        all_results = {
            "opportunities": [],
            "signals": [],
            "cross_pollinations": []
        }

        # Filter out search tasks (handled separately by scout engine)
        real_items = [
            item for item in content_items
            if not item.title.startswith("[SEARCH_TASK]")
        ]

        if not real_items:
            return all_results

        # Process in batches
        for i in range(0, len(real_items), batch_size):
            batch = real_items[i:i + batch_size]
            try:
                result = self._analyze_content_batch(batch)
                if result:
                    all_results["opportunities"].extend(
                        result.get("opportunities", [])
                    )
                    all_results["signals"].extend(
                        result.get("signals", [])
                    )
                    all_results["cross_pollinations"].extend(
                        result.get("cross_pollinations", [])
                    )
            except Exception as e:
                logger.error(f"Batch analysis failed: {e}")

        # Assign IDs and calculate weighted totals
        for idx, opp in enumerate(all_results["opportunities"]):
            if 'id' not in opp or not opp['id']:
                opp['id'] = f"OPP-{datetime.utcnow().strftime('%Y%m%d')}-{idx+1:03d}"
            opp['weighted_total'] = self._calculate_weighted_total(opp.get('scores', {}))
            opp['tier'] = self._determine_tier(opp['weighted_total'])

        return all_results

    def analyze_with_web_search(self, query: str, source_config: dict) -> dict:
        """
        Use Claude API with web_search tool to research a topic.
        This is the primary way the scout gathers real-time intelligence.
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self._system_prompt,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search"
                }],
                messages=[{
                    "role": "user",
                    "content": (
                        f"Search the web for the following and analyze any business "
                        f"opportunities or market signals you find. Be specific and "
                        f"score any opportunities according to the scoring rubric.\n\n"
                        f"SEARCH QUERY: {query}\n\n"
                        f"SOURCE CONTEXT: {json.dumps(source_config)}\n\n"
                        f"Return your analysis as the specified JSON format. If no "
                        f"clear opportunities are found, return signals only."
                    )
                }]
            )
            
            # Extract text content from response
            text_content = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text_content += block.text

            return self._parse_json_response(text_content)
            
        except Exception as e:
            logger.error(f"Web search analysis failed for '{query}': {e}")
            return {"opportunities": [], "signals": [], "cross_pollinations": []}

    def deep_dive(self, topic: str, existing_data: dict = None) -> dict:
        """
        Perform a deep dive analysis on a specific opportunity or topic.
        Uses Opus model for maximum analytical depth.
        """
        context = ""
        if existing_data:
            context = f"\n\nEXISTING ANALYSIS:\n{json.dumps(existing_data, indent=2)}"

        try:
            response = self.client.messages.create(
                model=self.model_deep,  # Use Opus for deep dives
                max_tokens=self.max_tokens_deep,
                system=self._system_prompt,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search"
                }],
                messages=[{
                    "role": "user",
                    "content": (
                        f"Perform a DEEP DIVE analysis on this opportunity/topic. "
                        f"Use web search extensively to validate every claim with "
                        f"real 2026 market data.\n\n"
                        f"TOPIC: {topic}\n"
                        f"{context}\n\n"
                        f"Your deep dive must cover:\n"
                        f"1. MARKET VALIDATION — TAM/SAM/SOM with real numbers\n"
                        f"2. COMPETITIVE LANDSCAPE — Name 3-5 real competitors with pricing\n"
                        f"3. TECHNICAL FEASIBILITY — Exact tech stack and build cost\n"
                        f"4. BUSINESS MODEL — Unit economics, pricing tiers\n"
                        f"5. RISK ASSESSMENT — Top 3 kill risks\n"
                        f"6. 90-DAY ACTION PLAN — Week-by-week execution\n"
                        f"7. FINANCIAL PROJECTIONS — Month 3, 6, 12 revenue estimates\n\n"
                        f"Be brutally honest. If this opportunity is weak, say so.\n\n"
                        f"Return the full analysis in the standard JSON format, "
                        f"with the deep dive data in a 'deep_dive' field."
                    )
                }]
            )

            text_content = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text_content += block.text

            return self._parse_json_response(text_content)

        except Exception as e:
            logger.error(f"Deep dive failed for '{topic}': {e}")
            return {"opportunities": [], "signals": [], "cross_pollinations": []}

    def score_idea(self, idea_description: str) -> dict:
        """
        Score a specific business idea against the 10-dimension model.
        Used for the /score command.
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self._system_prompt,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Score this business opportunity idea against the "
                        f"10-dimension scoring model. Be rigorous and specific "
                        f"in your scoring justifications.\n\n"
                        f"IDEA: {idea_description}\n\n"
                        f"Return as the standard JSON format with one opportunity."
                    )
                }]
            )

            text_content = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text_content += block.text

            result = self._parse_json_response(text_content)
            if result.get("opportunities"):
                opp = result["opportunities"][0]
                opp['weighted_total'] = self._calculate_weighted_total(opp.get('scores', {}))
                opp['tier'] = self._determine_tier(opp['weighted_total'])
            return result

        except Exception as e:
            logger.error(f"Scoring failed: {e}")
            return {"opportunities": [], "signals": [], "cross_pollinations": []}

    # ─── Internal Methods ───────────────────────────────────

    def _analyze_content_batch(self, items: list) -> dict:
        """Send a batch of content items to Claude for analysis."""
        items_text = "\n\n---\n\n".join([
            f"SOURCE: {item.source_name}\n"
            f"TITLE: {item.title}\n"
            f"URL: {item.url}\n"
            f"DATE: {item.published}\n"
            f"TAGS: {', '.join(item.tags)}\n"
            f"CONTENT:\n{item.content}"
            for item in items
        ])

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"Analyze the following {len(items)} content items. "
                    f"Extract any business opportunities or market signals. "
                    f"Score opportunities using the 10-dimension model. "
                    f"Look for cross-pollination opportunities between items.\n\n"
                    f"If no opportunities or signals exist, return empty arrays.\n\n"
                    f"CONTENT ITEMS:\n\n{items_text}"
                )
            }]
        )

        text_content = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text_content += block.text

        return self._parse_json_response(text_content)

    def _parse_json_response(self, text: str) -> dict:
        """Extract and parse JSON from Claude's response."""
        # Try to find JSON in the response
        try:
            # First try: direct JSON parse
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Second try: find JSON block in markdown
        import re
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Third try: find anything that looks like our JSON structure
        json_match = re.search(r'\{[\s\S]*"opportunities"[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse JSON from Claude response")
        logger.debug(f"Raw response: {text[:500]}")
        return {"opportunities": [], "signals": [], "cross_pollinations": []}

    def _calculate_weighted_total(self, scores: dict) -> float:
        """Calculate weighted total from dimension scores."""
        weights = self.config.get('scoring', {}).get('weights', {
            'founder_fit': 3.0,
            'ai_unlock': 2.5,
            'time_to_revenue': 2.5,
            'capital_efficiency': 2.0,
            'market_timing': 2.0,
            'defensibility': 1.5,
            'scale_potential': 1.5,
            'geographic_leverage': 1.5,
            'competition_gap': 1.0,
            'simplicity': 1.0
        })

        total = 0.0
        for dim, weight in weights.items():
            score_data = scores.get(dim, {})
            if isinstance(score_data, dict):
                score = score_data.get('score', 0)
            elif isinstance(score_data, (int, float)):
                score = score_data
            else:
                score = 0
            total += score * weight

        return round(total, 1)

    def _determine_tier(self, weighted_total: float) -> str:
        """Determine opportunity tier from weighted total."""
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

    def _default_system_prompt(self) -> str:
        return (
            "You are an analytical engine for OpportunityScout. "
            "Analyze content and extract business opportunities. "
            "Score each on 10 dimensions (1-10 each). "
            "Return valid JSON with 'opportunities', 'signals', "
            "and 'cross_pollinations' arrays."
        )
