"""
OpportunityScout — Main Engine (Orchestrator)

This is the central nervous system. It coordinates:
- Web scanning (content gathering)
- Opportunity scoring (Claude API analysis)  
- Knowledge base (persistence)
- Telegram notifications (output)
- Self-improvement (evolution)

Can be triggered by:
- n8n webhook (scheduled scans)
- Telegram command (manual scans)
- CLI (Claude Code commands)
- HTTP API (direct integration)
"""

import asyncio
import json
import logging
import time
import yaml
from datetime import datetime
from pathlib import Path

from .web_scanner import WebScanner, ContentItem
from .opportunity_scorer import OpportunityScorer
from .knowledge_base import KnowledgeBase
from .telegram_bot import TelegramNotifier
from .self_improver import SelfImprover
from .model_generator import BusinessModelGenerator
from .serendipity_engine import SerendipityEngine
from .localization_scanner import LocalizationScanner

logger = logging.getLogger("scout.engine")


class ScoutEngine:
    """
    The main orchestrator. Coordinates all scout subsystems.
    """

    def __init__(self, config_path: str = "./config/config.yaml"):
        # Load configuration
        self.config = self._load_config(config_path)
        self.sources = self._load_sources()

        # Initialize subsystems
        self.scanner = WebScanner(self.config)
        self.scorer = OpportunityScorer(self.config)
        self.kb = KnowledgeBase(
            self.config.get('database', {}).get('path', './data/opportunity_scout.db')
        )
        self.telegram = TelegramNotifier(self.config)
        self.improver = SelfImprover(self.config, self.kb)
        self.generator = BusinessModelGenerator(self.config, self.kb)
        self.serendipity = SerendipityEngine(self.config, self.kb)
        self.localizer = LocalizationScanner(self.config, self.kb)

        logger.info("🚀 OpportunityScout engine initialized")

    # ─── Core Scan Cycle ────────────────────────────────────

    async def run_scan_cycle(self, tier: int = 1) -> dict:
        """
        Run a complete scan cycle:
        1. Gather content from sources
        2. Analyze with Claude API
        3. Score and store opportunities
        4. Send alerts for high-score findings
        5. Log scan results
        
        Returns summary stats.
        """
        start_time = time.time()
        stats = {
            "sources_scanned": 0,
            "items_collected": 0,
            "opportunities_found": 0,
            "signals_found": 0,
            "fire_alerts": 0,
            "high_alerts": 0,
            "scan_duration": 0
        }

        logger.info(f"{'='*60}")
        logger.info(f"🔍 SCAN CYCLE START — Tier {tier}")
        logger.info(f"{'='*60}")

        # PHASE 1: GATHER
        logger.info("📡 Phase 1: Gathering content...")
        tier_sources = [s for s in self.sources if s.get('tier') == tier]
        stats["sources_scanned"] = len(tier_sources)
        
        all_items = await self.scanner.scan_sources(self.sources, tier=tier)
        stats["items_collected"] = len(all_items)
        logger.info(f"   Collected {len(all_items)} items from {len(tier_sources)} sources")

        # Separate real content from search tasks
        real_items = [i for i in all_items if not i.title.startswith("[SEARCH_TASK]")]
        search_tasks = [i for i in all_items if i.title.startswith("[SEARCH_TASK]")]

        # PHASE 2: ANALYZE — Real content batch analysis
        logger.info("🧠 Phase 2: Analyzing content with Claude...")
        
        all_opportunities = []
        all_signals = []
        all_cross_pollinations = []

        if real_items:
            result = self.scorer.analyze_batch(real_items, batch_size=5)
            all_opportunities.extend(result.get("opportunities", []))
            all_signals.extend(result.get("signals", []))
            all_cross_pollinations.extend(result.get("cross_pollinations", []))

        # PHASE 2b: Execute web search tasks via Claude API
        for task_item in search_tasks:
            try:
                task_data = json.loads(task_item.content)
                query = task_data.get("query", "")
                source_config = task_data.get("source_config", {})
                
                if query:
                    logger.info(f"   🔎 Web search: {query[:80]}...")
                    result = self.scorer.analyze_with_web_search(query, source_config)
                    all_opportunities.extend(result.get("opportunities", []))
                    all_signals.extend(result.get("signals", []))

                    # Log source performance
                    self.kb.log_source_scan(
                        source_name=task_item.source_name,
                        items_found=1,
                        opportunities=len(result.get("opportunities", [])),
                        avg_score=self._avg_score(result.get("opportunities", [])),
                        highest_score=self._max_score(result.get("opportunities", [])),
                        errors=0,
                        duration=0
                    )
            except Exception as e:
                logger.error(f"   Search task failed: {e}")

        # PHASE 3: STORE & DELIVER
        logger.info("💾 Phase 3: Storing and delivering results...")

        for opp in all_opportunities:
            # Check for duplicates
            if not self.kb.is_duplicate(opp.get('title', ''), opp.get('source', '')):
                opp_id = self.kb.save_opportunity(opp)
                stats["opportunities_found"] += 1

                # Send alerts based on tier
                tier_label = opp.get('tier', 'LOW')
                if tier_label == 'FIRE':
                    await self.telegram.send_fire_alert(opp)
                    stats["fire_alerts"] += 1
                    logger.info(f"   🔥 FIRE: {opp.get('title')} ({opp.get('weighted_total')})")
                elif tier_label == 'HIGH':
                    await self.telegram.send_high_alert(opp)
                    stats["high_alerts"] += 1
                    logger.info(f"   ⭐ HIGH: {opp.get('title')} ({opp.get('weighted_total')})")
                else:
                    logger.info(f"   📝 {tier_label}: {opp.get('title')} ({opp.get('weighted_total')})")

        for signal in all_signals:
            self.kb.save_signal(signal)
            stats["signals_found"] += 1

        for cp in all_cross_pollinations:
            self.kb.save_cross_pollination(
                cp.get('insight', ''),
                cp.get('opportunities_connected', []),
                cp.get('novel_angle', '')
            )

        # Track trends from tags
        for opp in all_opportunities:
            for tag in opp.get('tags', []):
                self.kb.track_trend(tag, opp.get('source', 'scan'))

        # PHASE 4: LOG
        duration = time.time() - start_time
        stats["scan_duration"] = round(duration, 1)

        self.kb.log_scan(
            scan_type=f"tier_{tier}",
            sources_scanned=stats["sources_scanned"],
            opportunities_found=stats["opportunities_found"],
            signals_found=stats["signals_found"],
            fire_alerts=stats["fire_alerts"],
            duration=duration,
            summary=json.dumps(stats)
        )

        logger.info(f"{'='*60}")
        logger.info(f"✅ SCAN COMPLETE — {stats['opportunities_found']} opportunities, "
                    f"{stats['fire_alerts']} fire alerts, {duration:.0f}s")
        logger.info(f"{'='*60}")

        return stats

    # ─── Daily Digest ───────────────────────────────────────

    async def generate_daily_digest(self):
        """Generate and send the daily intelligence digest."""
        logger.info("📊 Generating daily digest...")

        # Get today's top opportunities
        recent_opps = self.kb.get_recent_opportunities(hours=24)
        top_opps = sorted(
            recent_opps,
            key=lambda x: x.get('weighted_total', 0),
            reverse=True
        )[:5]

        # Get recent signals (simplified — just pull from DB)
        # In production, you'd have a more sophisticated signal aggregation
        signals = []  # TODO: Add signal aggregation from KB

        await self.telegram.send_daily_digest(top_opps, signals)
        logger.info(f"📊 Daily digest sent: {len(top_opps)} opportunities")

    # ─── Weekly Report ──────────────────────────────────────

    async def generate_weekly_report(self):
        """Generate and send comprehensive weekly report."""
        logger.info("📋 Generating weekly report...")

        stats = self.kb.get_stats()
        top_opps = self.kb.get_top_opportunities(limit=10)
        recent_opps = self.kb.get_recent_opportunities(hours=168)  # 7 days

        report_data = {
            "summary": (
                f"This week OpportunityScout discovered {len(recent_opps)} opportunities "
                f"across {stats.get('total_scans', 0)} scans. "
                f"{stats.get('fire_opportunities', 0)} FIRE-tier and "
                f"{stats.get('high_opportunities', 0)} HIGH-tier opportunities "
                f"are in the portfolio."
            ),
            "stats": {
                "new_opportunities": len(recent_opps),
                "fire_count": len([o for o in recent_opps if o.get('tier') == 'FIRE']),
                "sources_scanned": stats.get('total_scans', 0),
                "avg_score": stats.get('avg_score', 0)
            },
            "top_opportunities": top_opps,
            "evolutions": [],  # Populated by evolution cycle
            "recommended_actions": self._generate_action_recommendations(top_opps)
        }

        await self.telegram.send_weekly_report(report_data)
        logger.info("📋 Weekly report sent")

    # ─── Deep Dive ──────────────────────────────────────────

    async def run_deep_dive(self, topic: str) -> dict:
        """
        Run a deep dive analysis on a specific topic or opportunity.
        Uses Opus model for maximum analytical depth.
        """
        logger.info(f"🔬 Deep dive: {topic}")

        # Check if this is an existing opportunity ID
        existing = self.kb.get_opportunity(topic) if topic.startswith('OPP-') else None

        result = self.scorer.deep_dive(topic, existing)

        # Store results
        for opp in result.get("opportunities", []):
            self.kb.save_opportunity(opp)

        # Send to Telegram
        if result.get("opportunities"):
            for opp in result["opportunities"]:
                if opp.get('tier') == 'FIRE':
                    await self.telegram.send_fire_alert(opp)
                elif opp.get('tier') == 'HIGH':
                    await self.telegram.send_high_alert(opp)

        return result

    # ─── Score an Idea ──────────────────────────────────────

    async def score_idea(self, description: str) -> dict:
        """Score a specific business idea."""
        logger.info(f"📊 Scoring idea: {description[:80]}...")
        result = self.scorer.score_idea(description)

        if result.get("opportunities"):
            opp = result["opportunities"][0]
            self.kb.save_opportunity(opp)
            
            # Send scored result to Telegram
            scores = opp.get('scores', {})
            top_dims = []
            for dim, data in scores.items():
                score = data.get('score', 0) if isinstance(data, dict) else data
                top_dims.append((dim.replace('_', ' ').title(), score))
            top_dims.sort(key=lambda x: x[1], reverse=True)

            msg = (
                f"📊 IDEA SCORED\n\n"
                f"Title: {opp.get('title', 'N/A')}\n"
                f"Score: {opp.get('weighted_total', 0)}/185 ({opp.get('tier', 'N/A')})\n\n"
                f"Dimensions:\n"
            )
            for dim, score in top_dims:
                bar = "█" * score + "░" * (10 - score)
                msg += f"  {dim}: {bar} {score}/10\n"
            
            msg += f"\nFirst Move: {opp.get('first_move', 'N/A')}"

            await self.telegram.send_text(msg)

        return result

    # ─── Business Model Generation ────────────────────────

    async def generate_business_models(self, focus_area: str = None,
                                        count: int = 3) -> dict:
        """
        Generate novel business model ideas from accumulated intelligence.
        Uses Opus for creative synthesis, Sonnet for scoring, web search
        for validation. This is the highest-value operation in the system.
        """
        logger.info(f"💡 Starting business model generation cycle...")

        result = self.generator.generate(focus_area=focus_area, count=count)
        models = result.get('models', [])

        if not models:
            logger.warning("💡 No business models generated this cycle")
            await self.telegram.send_text(
                "💡 Business model generator ran but produced no ideas. "
                "This usually means insufficient accumulated data — run more "
                "scan cycles first."
            )
            return result

        # Send each model to Telegram
        for model in models:
            await self._send_model_to_telegram(model)

        # Send summary
        gen_ctx = result.get('generation_context', {})
        summary = (
            f"💡 BUSINESS MODEL GENERATION COMPLETE\n\n"
            f"Models generated: {len(models)}\n"
            f"Signals analyzed: {gen_ctx.get('signals_analyzed', 0)}\n"
            f"Trends analyzed: {gen_ctx.get('trends_analyzed', 0)}\n"
            f"Blind spots considered: {gen_ctx.get('blind_spots_found', 0)}\n"
        )
        if focus_area:
            summary += f"Focus area: {focus_area}\n"

        top_model = max(models, key=lambda m: m.get('weighted_total', 0))
        summary += (
            f"\nBest model: {top_model.get('title', 'N/A')} "
            f"({top_model.get('weighted_total', 0)}/185 — {top_model.get('tier', '?')})"
        )
        await self.telegram.send_text(summary)

        logger.info(f"💡 Generated {len(models)} business models")
        return result

    async def _send_model_to_telegram(self, model: dict):
        """Send a generated business model to Telegram with rich formatting."""
        gen = model.get('generated_model', {})
        customer = gen.get('customer', {})
        biz = gen.get('business_model', {})
        validation = model.get('validation', {})

        tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
            model.get('tier', ''), "📝"
        )
        confidence_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(
            gen.get('confidence', ''), "⚪"
        )

        msg = (
            f"💡 GENERATED BUSINESS MODEL\n"
            f"{'='*35}\n\n"
            f"{tier_emoji} {model.get('title', 'Untitled')}\n"
            f"Score: {model.get('weighted_total', 0)}/185\n"
            f"Confidence: {confidence_emoji} {gen.get('confidence', '?')}\n\n"
            f"{model.get('one_liner', '')}\n\n"
            f"ORIGIN:\n{gen.get('origin_story', 'N/A')[:200]}\n\n"
            f"PROBLEM:\n{gen.get('problem', 'N/A')[:200]}\n\n"
            f"SOLUTION:\n{gen.get('solution', 'N/A')[:200]}\n\n"
            f"AI UNLOCK:\n{gen.get('ai_unlock', 'N/A')[:150]}\n\n"
            f"CUSTOMER: {customer.get('who', 'N/A')}\n"
            f"Pain level: {customer.get('pain_level', '?')}/10\n"
            f"Current spend: {customer.get('current_spend', 'N/A')}\n\n"
            f"REVENUE: {biz.get('revenue_type', 'N/A')}\n"
            f"Pricing: {biz.get('pricing', 'N/A')}\n"
            f"Time to revenue: {biz.get('time_to_first_revenue', 'N/A')}\n\n"
            f"FOUNDER EDGE:\n{gen.get('founder_edge', 'N/A')[:200]}\n\n"
            f"FIRST MOVE:\n{gen.get('first_move', 'N/A')}\n\n"
            f"KILL CRITERIA:\n{gen.get('kill_criteria', 'N/A')}\n\n"
        )

        if validation.get('status') == 'validated':
            msg += f"WEB VALIDATION:\n{validation.get('findings', '')[:300]}\n\n"

        msg += f"ID: {model.get('id', 'N/A')}"

        await self.telegram.send_text(msg)

    # ─── Serendipity Engine ─────────────────────────────────

    async def run_serendipity_daily(self) -> dict:
        """
        Run the daily light serendipity scan.
        Searches broadly across all sectors, filters by founder fit.
        """
        logger.info("🎲 Running serendipity daily scan...")

        result = self.serendipity.daily_scan()
        opportunities = result.get('opportunities', [])

        for opp in opportunities:
            tier = opp.get('tier', 'LOW')
            if tier == 'FIRE':
                await self.telegram.send_fire_alert(opp)
            elif tier == 'HIGH':
                await self.telegram.send_high_alert(opp)

        if opportunities:
            summary = (
                f"🎲 SERENDIPITY DAILY SCAN\n\n"
                f"Searched broadly across all sectors.\n"
                f"Found: {result.get('raw_found', 0)} raw opportunities\n"
                f"Passed founder fit filter: {result.get('passed_filter', 0)}\n"
            )
            for opp in opportunities[:3]:
                tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
                    opp.get('tier', ''), "📝"
                )
                summary += (
                    f"\n{tier_emoji} {opp.get('title', '?')} "
                    f"({opp.get('weighted_total', 0)})"
                )
            await self.telegram.send_text(summary)

        logger.info(
            f"🎲 Serendipity daily: {result.get('passed_filter', 0)} "
            f"opportunities passed filter"
        )
        return result

    async def run_serendipity_weekly(self) -> dict:
        """
        Run the weekly deep serendipity analysis.
        Opus-powered, multi-step cross-sector research.
        """
        logger.info("🎲 Running serendipity weekly deep scan...")

        result = self.serendipity.weekly_deep_scan()
        opportunities = result.get('opportunities', [])

        for opp in opportunities:
            tier = opp.get('tier', 'LOW')
            if tier == 'FIRE':
                await self.telegram.send_fire_alert(opp)
            elif tier == 'HIGH':
                await self.telegram.send_high_alert(opp)

        if opportunities:
            summary = (
                f"🎲 SERENDIPITY WEEKLY DEEP SCAN\n\n"
                f"Opus analyzed trends across ALL sectors.\n"
                f"Found: {result.get('raw_found', 0)} raw opportunities\n"
                f"Passed founder fit filter: {result.get('passed_filter', 0)}\n"
            )
            for opp in opportunities[:5]:
                tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
                    opp.get('tier', ''), "📝"
                )
                summary += (
                    f"\n{tier_emoji} {opp.get('title', '?')} "
                    f"({opp.get('weighted_total', 0)})"
                )
                discovery = opp.get('discovery_path', '')
                if discovery:
                    summary += f"\n   💡 {discovery[:100]}"
            await self.telegram.send_text(summary)

        logger.info(
            f"🎲 Serendipity weekly: {result.get('passed_filter', 0)} "
            f"opportunities passed filter"
        )
        return result

    # ─── Localization Scanner (Samwer Lens) ────────────────

    async def run_localization_scan(self, focus_sector: str = None,
                                     count: int = 5) -> dict:
        """
        Run the Samwer/Rocket Internet localization scan.
        Finds proven models globally, checks UK/Turkey gaps.
        """
        logger.info("🌍 Running localization scan...")

        result = self.localizer.scan(focus_sector=focus_sector, count=count)
        opportunities = result.get('opportunities', [])

        for opp in opportunities:
            tier = opp.get('tier', 'LOW')
            if tier == 'FIRE':
                await self.telegram.send_fire_alert(opp)
            elif tier == 'HIGH':
                await self.telegram.send_high_alert(opp)

        if opportunities:
            summary = (
                f"🌍 LOCALIZATION SCAN COMPLETE\n"
                f"(Samwer/Rocket Internet lens)\n\n"
                f"Models analyzed: {result.get('models_analyzed', 0)}\n"
                f"Opportunities found: {result.get('opportunities_stored', 0)}\n"
            )
            if focus_sector:
                summary += f"Focus: {focus_sector}\n"

            for opp in opportunities[:5]:
                tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
                    opp.get('tier', ''), "📝"
                )
                original = opp.get('original_model', {})
                gap = opp.get('gap_analysis', {})

                summary += (
                    f"\n{tier_emoji} {opp.get('title', '?')} "
                    f"({opp.get('weighted_total', 0)})\n"
                    f"   Original: {original.get('company', '?')} "
                    f"({original.get('country', '?')}) — "
                    f"{original.get('funding', 'N/A')}\n"
                    f"   UK: {gap.get('uk_status', '?')} | "
                    f"TR: {gap.get('turkey_status', '?')}\n"
                    f"   First move: {opp.get('first_move', 'N/A')[:80]}"
                )

            await self.telegram.send_text(summary)

        logger.info(
            f"🌍 Localization scan: {result.get('opportunities_stored', 0)} "
            f"opportunities found"
        )
        return result

    # ─── Evolution ──────────────────────────────────────────

    async def run_evolution_cycle(self):
        """Run the self-improvement cycle."""
        logger.info("🧬 Running evolution cycle...")
        changes = self.improver.run_evolution_cycle()
        if changes:
            await self.telegram.send_evolution_notification(changes)
        return changes

    # ─── Helpers ────────────────────────────────────────────

    def _load_config(self, path: str) -> dict:
        """Load YAML configuration."""
        try:
            with open(path) as f:
                config = yaml.safe_load(f)
            # Resolve environment variables
            return self._resolve_env_vars(config)
        except FileNotFoundError:
            logger.warning(f"Config not found at {path}, using defaults")
            return {}

    def _load_sources(self) -> list:
        """Load sources configuration."""
        try:
            with open("./config/sources.yaml") as f:
                data = yaml.safe_load(f)
            return data.get('sources', [])
        except FileNotFoundError:
            logger.warning("Sources config not found, using empty list")
            return []

    def _resolve_env_vars(self, obj):
        """Recursively resolve ${VAR} patterns in config values."""
        import os
        if isinstance(obj, str):
            if obj.startswith('${') and obj.endswith('}'):
                var_name = obj[2:-1]
                return os.environ.get(var_name, obj)
            return obj
        elif isinstance(obj, dict):
            return {k: self._resolve_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_env_vars(item) for item in obj]
        return obj

    @staticmethod
    def _avg_score(opportunities: list) -> float:
        """Calculate average weighted score."""
        if not opportunities:
            return 0
        scores = [o.get('weighted_total', 0) for o in opportunities]
        return round(sum(scores) / len(scores), 1)

    @staticmethod
    def _max_score(opportunities: list) -> float:
        """Get maximum weighted score."""
        if not opportunities:
            return 0
        return max(o.get('weighted_total', 0) for o in opportunities)

    def _generate_action_recommendations(self, top_opps: list) -> list:
        """Generate prioritized action recommendations from top opportunities."""
        actions = []
        for opp in top_opps[:5]:
            if opp.get('tier') in ['FIRE', 'HIGH']:
                actions.append(
                    f"[{opp.get('tier')}] {opp.get('title')}: "
                    f"{opp.get('first_move', 'Review this opportunity')}"
                )
        return actions
