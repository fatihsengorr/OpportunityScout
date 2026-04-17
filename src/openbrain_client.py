"""
OpportunityScout — Open Brain Integration Client

Bidirectional bridge between OpportunityScout and Open Brain:
- Phase 1: Push discovered opportunities into Brain (intelligence/opportunities)
- Phase 2: Pull operator context from Brain to enrich scoring
- Phase 3: Unified search across both systems

Open Brain API: Supabase Edge Function with /ingest webhook + MCP HTTP transport
"""

import json
import logging
import os
from datetime import datetime

import httpx

logger = logging.getLogger("scout.openbrain")

OPENBRAIN_URL = "https://aymebtbqcofdppxtmtdw.supabase.co/functions/v1/open-brain-mcp"
DEFAULT_PATH = "intelligence/opportunities"


class OpenBrainClient:
    """Client for Open Brain MCP server via HTTP API."""

    def __init__(self, config: dict = None):
        self.api_key = os.environ.get("OPENBRAIN_API_KEY", "")
        self.base_url = os.environ.get("OPENBRAIN_URL", OPENBRAIN_URL)
        self.enabled = bool(self.api_key)

        if not self.enabled:
            logger.warning("Open Brain not configured (OPENBRAIN_API_KEY missing)")

    # ─── Phase 1: Scout → Brain ─────────────────────────────

    async def push_opportunity(self, opportunity: dict) -> dict | None:
        """
        Push a discovered opportunity into Open Brain.
        Uses the /ingest webhook endpoint.

        NOTE: Open Brain v2 ingest schema accepts only {path, content}.
        Metadata (tier, score, tags) is embedded inline in content as markdown
        front-matter — Brain's semantic search still finds it there.
        """
        if not self.enabled:
            return None

        sector = opportunity.get("sector") or "uncategorized"
        # Normalize sector for path (lowercase, no spaces, no slashes)
        safe_sector = (sector.lower()
                       .replace(' ', '-')
                       .replace('/', '-')
                       .replace('&', 'and'))

        # Build rich content — metadata now embedded as markdown front-matter
        content = self._format_opportunity_for_brain(opportunity)

        payload = {
            "content": content,
            "path": f"intelligence/opportunities/{safe_sector}",
        }

        return await self._ingest(payload)

    async def push_signal(self, signal: dict) -> dict | None:
        """Push a market signal into Open Brain."""
        if not self.enabled:
            return None

        tags = signal.get("tags", [])
        if isinstance(tags, list):
            tags_str = ', '.join(tags)
        else:
            tags_str = str(tags)

        content = (
            f"Market Signal: {signal.get('summary', 'N/A')}\n"
            f"Source: {signal.get('source', 'N/A')}\n"
            f"Relevance: {signal.get('relevance', 'N/A')}\n"
            f"Tags: {tags_str}\n"
            f"Detected: {datetime.utcnow().strftime('%Y-%m-%d')}"
        )

        return await self._ingest({
            "content": content,
            "path": "intelligence/market-signals",
        })

    async def push_weekly_summary(self, report_data: dict) -> dict | None:
        """Push weekly report summary into Brain as a document."""
        if not self.enabled:
            return None

        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        stats = report_data.get("stats", {})
        top_opps = report_data.get("top_opportunities", [])

        opp_lines = []
        for opp in top_opps[:10]:
            opp_lines.append(
                f"- [{opp.get('tier', '?')}] {opp.get('title', '?')} "
                f"(Score: {opp.get('weighted_total', 0)})"
            )

        content = (
            f"OpportunityScout Weekly Report — {date_str}\n\n"
            f"{report_data.get('summary', 'No summary.')}\n\n"
            f"Stats:\n"
            f"- New opportunities: {stats.get('new_opportunities', 0)}\n"
            f"- FIRE alerts: {stats.get('fire_count', 0)}\n"
            f"- Sources scanned: {stats.get('sources_scanned', 0)}\n"
            f"- Avg score: {stats.get('avg_score', 0)}\n\n"
            f"Top Opportunities:\n" + "\n".join(opp_lines)
        )

        actions = report_data.get("recommended_actions", [])
        if actions:
            content += "\n\nRecommended Actions:\n"
            for i, action in enumerate(actions, 1):
                content += f"{i}. {action}\n"

        return await self._ingest({
            "content": content,
            "path": f"intelligence/opportunities/weekly-{date_str}",
        })

    # ─── Phase 2: Brain → Scout ─────────────────────────────

    async def get_operator_context(self) -> dict:
        """
        Pull operator context from Brain to enrich opportunity scoring.
        Returns structured context about capabilities, active projects,
        market intelligence, and strategic priorities.
        """
        if not self.enabled:
            return {}

        context = {}

        # 1. Get brain map for structural overview + priorities
        brain_map = await self._mcp_call("get_brain_map", {})
        if brain_map:
            context["brain_map"] = brain_map

        # 2. Search for active capabilities and assets
        capabilities = await self._mcp_call(
            "search_thoughts",
            {"query": "capabilities assets CNC production factory", "path": "context/", "limit": 5},
        )
        if capabilities:
            context["capabilities"] = capabilities

        # 3. Get active projects
        projects = await self._mcp_call(
            "list_thoughts",
            {"path": "projects/", "limit": 10},
        )
        if projects:
            context["active_projects"] = projects

        # 4. Get market intelligence
        intel = await self._mcp_call(
            "search_thoughts",
            {"query": "market opportunity trend strategy", "path": "intelligence/", "limit": 5},
        )
        if intel:
            context["market_intel"] = intel

        # 5. Get team/resource context
        team = await self._mcp_call(
            "list_thoughts",
            {"path": "context/team", "limit": 5},
        )
        if team:
            context["team"] = team

        logger.info(f"📧 Pulled operator context from Brain: {len(context)} sections")
        return context

    async def search_brain(self, query: str, path: str = None, limit: int = 5) -> list:
        """
        Search Open Brain semantically. Used for:
        - Telegram /brain command
        - Cross-referencing opportunities with existing knowledge
        """
        if not self.enabled:
            return []

        params = {"query": query, "limit": limit}
        if path:
            params["path"] = path

        result = await self._mcp_call("search_thoughts", params)
        return result if result else []

    async def get_brain_stats(self) -> dict:
        """Get Brain statistics."""
        if not self.enabled:
            return {}

        result = await self._mcp_call("thought_stats", {})
        return result if result else {}

    async def is_semantic_duplicate(self, title: str, one_liner: str = "",
                                      threshold: float = 0.70) -> bool:
        """
        Check if a semantically similar opportunity already exists in Brain.
        Uses Open Brain's hybrid search with a high similarity threshold.
        Returns True if a close match is found.
        """
        if not self.enabled:
            return False

        query = f"{title} {one_liner}".strip()
        if not query:
            return False

        results = await self._mcp_call(
            "search_thoughts",
            {
                "query": query,
                "path": "intelligence/opportunities",
                "limit": 3,
                "threshold": threshold,
            },
        )

        if not results:
            return False

        # Parse results — check if any match exceeds threshold
        if isinstance(results, str):
            # Check for high similarity matches in the text response
            import re
            matches = re.findall(r'(\d+\.?\d*)% match', results)
            for match_pct in matches:
                if float(match_pct) >= threshold * 100:
                    logger.info(
                        f"🔄 Semantic duplicate found ({match_pct}%): {title[:60]}"
                    )
                    return True

        return False

    # ─── Phase 3: Context Enrichment for Scoring ────────────

    def build_scoring_context(self, brain_context: dict) -> str:
        """
        Convert Brain context into a structured prompt addition
        for the opportunity scorer. This replaces the hardcoded
        operator profile with live data from Open Brain.
        """
        if not brain_context:
            return ""

        sections = []

        # Brain map = strategic overview
        if brain_context.get("brain_map"):
            sections.append(
                "=== OPERATOR STRATEGIC CONTEXT (from Open Brain) ===\n"
                + str(brain_context["brain_map"])[:2000]
            )

        # Capabilities
        if brain_context.get("capabilities"):
            caps = brain_context["capabilities"]
            if isinstance(caps, list):
                cap_text = "\n".join(
                    [f"- {c.get('content', str(c))[:200]}" for c in caps[:5]]
                )
            else:
                cap_text = str(caps)[:500]
            sections.append(f"=== OPERATOR CAPABILITIES ===\n{cap_text}")

        # Active projects
        if brain_context.get("active_projects"):
            projs = brain_context["active_projects"]
            if isinstance(projs, list):
                proj_text = "\n".join(
                    [f"- {p.get('content', str(p))[:150]}" for p in projs[:8]]
                )
            else:
                proj_text = str(projs)[:500]
            sections.append(f"=== ACTIVE PROJECTS ===\n{proj_text}")

        # Market intel
        if brain_context.get("market_intel"):
            intel = brain_context["market_intel"]
            if isinstance(intel, list):
                intel_text = "\n".join(
                    [f"- {i.get('content', str(i))[:200]}" for i in intel[:5]]
                )
            else:
                intel_text = str(intel)[:500]
            sections.append(f"=== MARKET INTELLIGENCE ===\n{intel_text}")

        return "\n\n".join(sections)

    # ─── Internal HTTP Methods ──────────────────────────────

    async def _ingest(self, payload: dict) -> dict | None:
        """Send data to Open Brain /ingest endpoint."""
        # Circuit breaker: stop after 3 consecutive failures
        if getattr(self, '_ingest_failures', 0) >= 3:
            return None
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/ingest",
                    json=payload,
                    headers={
                        "x-brain-key": self.api_key,
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code == 200:
                    self._ingest_failures = 0
                    data = resp.json()
                    logger.info(
                        f"✅ Brain ingest OK: {payload.get('path')} "
                        f"(id={data.get('id', '?')})"
                    )
                    return data
                else:
                    self._ingest_failures = getattr(self, '_ingest_failures', 0) + 1
                    logger.error(
                        f"❌ Brain ingest failed [{resp.status_code}]: {resp.text[:200]}"
                    )
                    if self._ingest_failures >= 3:
                        logger.warning("⚡ Brain ingest circuit breaker tripped — skipping remaining ingests this cycle")
                    return None
        except Exception as e:
            logger.error(f"❌ Brain ingest error: {e}")
            return None

    async def _mcp_call(self, tool_name: str, arguments: dict) -> any:
        """
        Call an MCP tool via HTTP transport.
        Open Brain MCP server accepts standard MCP JSON-RPC over HTTP.
        """
        try:
            request_body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.base_url,
                    json=request_body,
                    headers={
                        "x-brain-key": self.api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                )

                if resp.status_code == 200:
                    # Response may be SSE (text/event-stream) or JSON
                    content_type = resp.headers.get("content-type", "")
                    if "text/event-stream" in content_type:
                        data = self._parse_sse_response(resp.text)
                    else:
                        data = resp.json()

                    # MCP response: {"result": {"content": [{"type": "text", "text": "..."}]}}
                    result = data.get("result", {})
                    content = result.get("content", [])
                    if content and isinstance(content, list):
                        text = content[0].get("text", "")
                        # Try to parse as JSON if possible
                        try:
                            return json.loads(text)
                        except (json.JSONDecodeError, TypeError):
                            return text
                    return result
                else:
                    logger.error(
                        f"❌ Brain MCP call {tool_name} failed [{resp.status_code}]: "
                        f"{resp.text[:200]}"
                    )
                    return None
        except Exception as e:
            logger.error(f"❌ Brain MCP call {tool_name} error: {e}")
            return None

    @staticmethod
    def _parse_sse_response(text: str) -> dict:
        """Parse Server-Sent Events response to extract JSON data."""
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                try:
                    return json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
        return {}

    # ─── Helpers ────────────────────────────────────────────

    @staticmethod
    def _format_opportunity_for_brain(opp: dict) -> str:
        """Format an opportunity as rich text for Brain storage."""
        risks = opp.get("risks", [])
        if isinstance(risks, str):
            try:
                risks = json.loads(risks)
            except (json.JSONDecodeError, TypeError):
                risks = [risks]

        tags = opp.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = [tags]

        return (
            f"Opportunity: {opp.get('title', 'Untitled')}\n"
            f"Score: {opp.get('weighted_total', 0)}/155 ({opp.get('tier', '?')})\n"
            f"Sector: {opp.get('sector', 'N/A')}\n\n"
            f"{opp.get('one_liner', '')}\n\n"
            f"Why NOW: {opp.get('why_now', 'N/A')}\n"
            f"First Move: {opp.get('first_move', 'N/A')}\n"
            f"Revenue Path: {opp.get('revenue_path', 'N/A')}\n"
            f"Risks: {', '.join(risks[:5])}\n"
            f"Tags: {', '.join(tags)}\n"
            f"Source: {opp.get('source', 'N/A')}\n"
            f"Scout ID: {opp.get('id', 'N/A')}\n"
            f"Detected: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )
