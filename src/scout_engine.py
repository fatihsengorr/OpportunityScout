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
from .email_reporter import EmailReporter
from .openbrain_client import OpenBrainClient
from .self_improver import SelfImprover
from .model_generator import BusinessModelGenerator
from .serendipity_engine import SerendipityEngine
from .localization_scanner import LocalizationScanner
from .capability_explorer import CapabilityExplorer
from .temporal_intelligence import TemporalIntelligence
from .competitive_monitor import CompetitiveMonitor
from .cross_pollinator import CrossPollinator
from .event_bus import EventBus
from .horizon_scanner import HorizonScanner
from .action_kit_generator import ActionKitGenerator
from .financial_modeler import FinancialModeler
from .claim_validator import ClaimValidator
from .consensus_scorer import ConsensusScorer
from .signal_scanner import SignalScanner
from .pattern_matcher import PatternMatcher
from .wow_threshold import WowThreshold
from .wildcatter_mode1 import WildcatterMode1
from .wildcatter_mode2 import WildcatterMode2
from .wildcatter_layers import WildcatterLayers
from .family5_cost_curves import CostCurvesTracker
from .family1_science_scanner import ScienceScanner
from .family2_infra_scanner import InfraLaunchScanner
from .scorer_audit import ScorerAudit

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
        self.email = EmailReporter(self.config)
        self.brain = OpenBrainClient(self.config)
        self.improver = SelfImprover(self.config, self.kb)  # event_bus wired after init
        self.generator = BusinessModelGenerator(self.config, self.kb)
        self.serendipity = SerendipityEngine(self.config, self.kb)
        self.localizer = LocalizationScanner(self.config, self.kb)
        self.explorer = CapabilityExplorer(self.config, self.kb)
        self.horizon = HorizonScanner(self.config, self.kb)
        self.action_kit = ActionKitGenerator(self.config, self.kb)
        self.financial = FinancialModeler(self.config, self.kb)
        self.validator = ClaimValidator(self.config, self.kb)
        self.consensus = ConsensusScorer(self.config, self.kb)
        self.signals = SignalScanner(self.config, self.kb)
        self.patterns = PatternMatcher(self.config, self.kb)
        self.wow = WowThreshold(self.config, self.kb)
        self.mode1 = WildcatterMode1(self.config, self.kb, self.brain)
        self.mode2 = WildcatterMode2(self.config, self.kb, self.patterns, self.wow)
        self.layers = WildcatterLayers(self.config, self.kb, self.brain,
                                        self.patterns, self.wow)
        self.family5 = CostCurvesTracker(self.config, self.kb)
        self.family1 = ScienceScanner(self.config, self.kb)
        self.family2 = InfraLaunchScanner(self.config, self.kb)
        self.scorer_audit = ScorerAudit(self.config, self.kb, self.brain)

        # Initialize Intelligence Mesh event bus
        self.event_bus = EventBus(self.kb)
        self.improver.event_bus = self.event_bus  # Wire event bus into self-improver

        # Phase 5 modules (wired to event bus)
        self.temporal = TemporalIntelligence(self.config, self.kb, self.event_bus)
        self.competitors = CompetitiveMonitor(self.config, self.kb, self.event_bus)
        self.crosspoll = CrossPollinator(self.config, self.kb, self.event_bus)

        self._wire_event_handlers()

        logger.info("🚀 OpportunityScout engine initialized (Intelligence Mesh active)")

    def _wire_event_handlers(self):
        """Wire up event bus subscriptions between modules."""
        # For now, register logging handlers for all event types.
        # As modules are upgraded to multi-strategy engines (Phase 2+),
        # they'll register their own handlers.
        event_types = [
            'signal_detected', 'opportunity_scored', 'blind_spot_found',
            'trend_cluster', 'operator_feedback', 'deadline_approaching',
            'negative_evidence', 'cross_pollination'
        ]
        for et in event_types:
            self.event_bus.subscribe(et, self._log_event)

    def _log_event(self, data: dict):
        """Default event handler — logs all events for debugging."""
        logger.debug(f"📡 Event received: {data.get('event_type', '?')}")

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
            "scan_duration": 0,
            "_opportunities": []  # internal: for scan report
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

        # PHASE 1.5: PULL OPERATOR CONTEXT FROM BRAIN
        brain_context = await self.brain.get_operator_context()
        scoring_context = self.brain.build_scoring_context(brain_context)
        if scoring_context:
            logger.info("🧠 Brain context loaded — scoring will use live operator profile")

        # PHASE 2: ANALYZE — Real content batch analysis
        logger.info("🧠 Phase 2: Analyzing content with Claude...")

        all_opportunities = []
        all_signals = []
        all_cross_pollinations = []

        if real_items:
            result = self.scorer.analyze_batch(real_items, batch_size=5, extra_context=scoring_context)
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

                    # Assign IDs, weighted totals and tiers (web search doesn't do this)
                    for opp in result.get("opportunities", []):
                        # ID is assigned by knowledge_base.save_opportunity() — no need to set here
                        opp['weighted_total'] = self.scorer._calculate_weighted_total(opp.get('scores', {}))
                        opp['tier'] = self.scorer._determine_tier(opp['weighted_total'])

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
            # Check for duplicates — Layer 1: SQLite fuzzy title match
            if self.kb.is_duplicate(opp.get('title', ''), opp.get('source', ''),
                                      sector=opp.get('sector', ''), tags=opp.get('tags', [])):
                logger.info(f"   🔄 Skip (DB duplicate): {opp.get('title', '?')[:60]}")
                continue

            # Check for duplicates — Layer 2: Open Brain semantic similarity
            if opp.get('tier') in ('FIRE', 'HIGH'):
                is_dup = await self.brain.is_semantic_duplicate(
                    opp.get('title', ''), opp.get('one_liner', '')
                )
                if is_dup:
                    logger.info(f"   🔄 Skip (semantic duplicate): {opp.get('title', '?')[:60]}")
                    continue

            opp_id = self.kb.save_opportunity(opp)
            stats["opportunities_found"] += 1
            stats["_opportunities"].append(opp)

            # Publish to Intelligence Mesh event bus
            self.event_bus.publish('opportunity_scored', {
                'id': opp.get('id'),
                'title': opp.get('title'),
                'tier': opp.get('tier'),
                'sector': opp.get('sector'),
                'weighted_total': opp.get('weighted_total'),
                'tags': opp.get('tags', [])
            }, source_module='web_scanner')

            # Push to Open Brain (only FIRE and HIGH — avoid noise)
            if opp.get('tier') in ('FIRE', 'HIGH'):
                await self.brain.push_opportunity(opp)

                # Send alerts based on tier
                tier_label = opp.get('tier', 'LOW')
                if tier_label == 'FIRE':
                    # Validate claims before alerting (~$0.01-0.02, adds ~15s latency)
                    await self._send_fire_alert_with_validation(opp)
                    await self.email.send_fire_alert(opp)
                    stats["fire_alerts"] += 1
                    logger.info(f"   🔥 FIRE: {opp.get('title')} ({opp.get('weighted_total')})")
                elif tier_label == 'HIGH':
                    await self.telegram.send_high_alert(opp)
                    await self.email.send_high_alert(opp)
                    stats["high_alerts"] += 1
                    logger.info(f"   ⭐ HIGH: {opp.get('title')} ({opp.get('weighted_total')})")
                else:
                    logger.info(f"   📝 {tier_label}: {opp.get('title')} ({opp.get('weighted_total')})")

        for signal in all_signals:
            self.kb.save_signal(signal)
            await self.brain.push_signal(signal)
            stats["signals_found"] += 1

            # Publish signal to Intelligence Mesh
            self.event_bus.publish('signal_detected', {
                'type': signal.get('type', 'market'),
                'summary': signal.get('summary', ''),
                'tags': signal.get('tags', []),
                'source': signal.get('source', '')
            }, source_module='web_scanner')

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

    async def run_full_scan(self, tiers: list = None) -> dict:
        """
        Run scan across multiple tiers and send a comprehensive report email.
        """
        if tiers is None:
            tiers = [1, 2, 3]

        start_time = time.time()
        all_opportunities = []
        tier_stats = {}

        for t in tiers:
            result = await self.run_scan_cycle(tier=t)
            tier_stats[f"Tier {t}"] = result
            all_opportunities.extend(result.get('_opportunities', []))

        total_duration = time.time() - start_time

        scan_results = {
            "tiers_scanned": tiers,
            "tier_stats": tier_stats,
            "total_duration": total_duration,
            "brain_synced": len(all_opportunities),
            "combined_stats": {
                "sources_scanned": sum(t.get('sources_scanned', 0) for t in tier_stats.values()),
                "opportunities_found": sum(t.get('opportunities_found', 0) for t in tier_stats.values()),
                "fire_alerts": sum(t.get('fire_alerts', 0) for t in tier_stats.values()),
                "high_alerts": sum(t.get('high_alerts', 0) for t in tier_stats.values()),
            }
        }

        # Send comprehensive scan report email
        await self.email.send_scan_report(scan_results, all_opportunities)

        logger.info(
            f"📧 Scan report email sent: {len(tiers)} tiers, "
            f"{len(all_opportunities)} opportunities, {total_duration:.0f}s"
        )

        return scan_results

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
        await self.email.send_daily_digest(top_opps, signals)
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
        await self.email.send_weekly_report(report_data)
        await self.brain.push_weekly_summary(report_data)
        logger.info("📋 Weekly report sent (Telegram + Email + Brain)")

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
                    await self._send_fire_alert_with_validation(opp)
                elif opp.get('tier') == 'HIGH':
                    await self._send_high_alert_with_brain(opp)

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
                f"Score: {opp.get('weighted_total', 0)}/155 ({opp.get('tier', 'N/A')})\n\n"
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

        # Show lens breakdown
        lens_results = gen_ctx.get('lens_results', {})
        if lens_results:
            summary += "\n📐 Lens breakdown:\n"
            for lens_name, lr in lens_results.items():
                if isinstance(lr, dict) and 'error' not in lr:
                    summary += f"  {lens_name}: {lr.get('raw_count', 0)} raw models\n"

        top_model = max(models, key=lambda m: m.get('weighted_total', 0))
        summary += (
            f"\nBest model: {top_model.get('title', 'N/A')} "
            f"({top_model.get('weighted_total', 0)}/155 — {top_model.get('tier', '?')})"
        )
        await self.telegram.send_text(summary)

        # Send activity report email
        if models:
            await self.email.send_activity_report(
                activity_type="generate",
                opportunities=models,
                extra_info={
                    "signals_analyzed": gen_ctx.get('signals_analyzed', 0),
                    "trends_analyzed": gen_ctx.get('trends_analyzed', 0),
                    "blind_spots_found": gen_ctx.get('blind_spots_found', 0),
                    "focus_area": focus_area or "All areas",
                }
            )

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
            f"Score: {model.get('weighted_total', 0)}/155\n"
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
                await self._send_fire_alert_with_validation(opp)
            elif tier == 'HIGH':
                await self._send_high_alert_with_brain(opp)

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

        # Send activity report email
        if opportunities:
            await self.email.send_activity_report(
                activity_type="serendipity",
                opportunities=opportunities,
                extra_info={
                    "raw_found": result.get('raw_found', 0),
                    "passed_filter": result.get('passed_filter', 0),
                    "scan_type": "Daily Light Scan",
                }
            )

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
                await self._send_fire_alert_with_validation(opp)
            elif tier == 'HIGH':
                await self._send_high_alert_with_brain(opp)

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

        # Send activity report email
        if opportunities:
            await self.email.send_activity_report(
                activity_type="serendipity",
                opportunities=opportunities,
                extra_info={
                    "raw_found": result.get('raw_found', 0),
                    "passed_filter": result.get('passed_filter', 0),
                    "scan_type": "Weekly Deep Scan (Opus)",
                }
            )

        logger.info(
            f"🎲 Serendipity weekly: {result.get('passed_filter', 0)} "
            f"opportunities passed filter"
        )
        return result

    # ─── Horizon Scanner (7-Lens Unbounded Discovery) ──────

    async def run_horizon_daily(self) -> dict:
        """Run 3 rotating horizon lenses for broad daily discovery."""
        logger.info("🔭 Running horizon daily scan...")

        result = self.horizon.daily_scan()
        opportunities = result.get('opportunities', [])

        for opp in opportunities:
            tier = opp.get('tier', 'LOW')
            if tier == 'FIRE':
                await self._send_fire_alert_with_validation(opp)
            elif tier == 'HIGH':
                await self._send_high_alert_with_brain(opp)

        if opportunities:
            lens_info = result.get('lens_results', {})
            lens_summary = ' | '.join(
                f"{k}: {v.get('found', 0)}" for k, v in lens_info.items()
                if isinstance(v, dict) and 'found' in v
            )
            frontiers = result.get('new_frontiers', [])
            summary = (
                f"🔭 HORIZON DAILY SCAN\n\n"
                f"Lenses: {lens_summary}\n"
                f"Total: {len(opportunities)} opportunities\n"
                f"New frontiers: {len(frontiers)}\n"
            )
            for opp in opportunities[:5]:
                tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
                    opp.get('tier', ''), "📝"
                )
                summary += (
                    f"\n{tier_emoji} {opp.get('title', '?')} "
                    f"({opp.get('weighted_total', 0)}/155)"
                )
            if frontiers:
                summary += f"\n\n🌱 Discovered: {', '.join(frontiers[:5])}"
            await self.telegram.send_text(summary)

        if opportunities:
            await self.email.send_activity_report(
                activity_type="serendipity",
                opportunities=opportunities,
                extra_info={
                    "scan_type": "Horizon Daily Scan (3 Lenses)",
                    "lenses_run": ', '.join(result.get('lens_results', {}).keys()),
                    "new_frontiers": len(result.get('new_frontiers', [])),
                }
            )

        logger.info(f"🔭 Horizon daily: {len(opportunities)} opportunities found")
        return result

    async def run_horizon_weekly(self) -> dict:
        """Run ALL 7 horizon lenses with Opus for deep weekly discovery."""
        logger.info("🔭 Running horizon weekly deep scan...")

        result = self.horizon.weekly_deep_scan()
        opportunities = result.get('opportunities', [])

        for opp in opportunities:
            tier = opp.get('tier', 'LOW')
            if tier == 'FIRE':
                await self._send_fire_alert_with_validation(opp)
            elif tier == 'HIGH':
                await self._send_high_alert_with_brain(opp)

        if opportunities:
            frontiers = result.get('new_frontiers', [])
            summary = (
                f"🔭 HORIZON WEEKLY DEEP SCAN (ALL 7 LENSES)\n\n"
                f"Total: {len(opportunities)} opportunities\n"
                f"New frontiers: {len(frontiers)}\n"
            )
            for opp in opportunities[:7]:
                tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
                    opp.get('tier', ''), "📝"
                )
                discovery = opp.get('discovery_path', '')
                summary += (
                    f"\n{tier_emoji} {opp.get('title', '?')} "
                    f"({opp.get('weighted_total', 0)}/155)"
                )
                if discovery:
                    summary += f"\n   💡 {discovery[:100]}"
            if frontiers:
                summary += f"\n\n🌱 New frontiers: {', '.join(frontiers[:10])}"
            await self.telegram.send_text(summary)

        if opportunities:
            await self.email.send_activity_report(
                activity_type="serendipity",
                opportunities=opportunities,
                extra_info={
                    "scan_type": "Horizon Weekly Deep Scan (7 Lenses, Opus)",
                    "new_frontiers": len(result.get('new_frontiers', [])),
                }
            )

        logger.info(f"🔭 Horizon weekly: {len(opportunities)} opportunities found")
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
                await self._send_fire_alert_with_validation(opp)
            elif tier == 'HIGH':
                await self._send_high_alert_with_brain(opp)

        if opportunities:
            summary = (
                f"🌍 LOCALIZATION 5-STRATEGY SCAN COMPLETE\n\n"
                f"Models analyzed: {result.get('models_analyzed', 0)}\n"
                f"Opportunities found: {result.get('opportunities_stored', 0)}\n"
            )
            if focus_sector:
                summary += f"Focus: {focus_sector}\n"

            # Show strategy breakdown
            strategy_results = result.get('strategy_results', {})
            if strategy_results:
                summary += "\n📊 Strategy breakdown:\n"
                for sname, sr in strategy_results.items():
                    if isinstance(sr, dict) and 'error' not in sr:
                        summary += (
                            f"  {sname}: {sr.get('stored', 0)} opps, "
                            f"best={sr.get('best', 0)}\n"
                        )

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

        # Send activity report email
        if opportunities:
            await self.email.send_activity_report(
                activity_type="localize",
                opportunities=opportunities,
                extra_info={
                    "models_analyzed": result.get('models_analyzed', 0),
                    "opportunities_stored": result.get('opportunities_stored', 0),
                    "focus_sector": focus_sector or "All sectors",
                }
            )

        logger.info(
            f"🌍 Localization scan: {result.get('opportunities_stored', 0)} "
            f"opportunities found"
        )
        return result

    # ─── Action Kit Generator ─────────────────────────────────

    async def run_action_kit(self, opp_id: str) -> dict:
        """Generate an action kit for an opportunity and deliver via Telegram + email."""
        logger.info(f"🎬 Generating action kit for {opp_id}...")

        # Fetch opportunity
        cursor = self.kb.conn.cursor()
        cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
        row = cursor.fetchone()
        if not row:
            await self.telegram.send_text(f"❌ Opportunity `{opp_id}` not found.")
            return {"error": "not_found"}
        opp = dict(row)

        # Generate kit (Claude Sonnet, ~30-45 seconds, ~$0.10-0.15)
        try:
            kit = self.action_kit.generate(opp_id)
        except Exception as e:
            logger.error(f"Action kit generation failed: {e}")
            await self.telegram.send_text(f"❌ Action kit failed: {e}")
            return {"error": str(e)}

        if kit.get('_parse_error'):
            await self.telegram.send_text(
                f"⚠️ Action kit JSON parse failed for `{opp_id}`. "
                f"Raw response saved."
            )
            return kit

        # Format for Telegram (condensed) + email (full HTML)
        md_summary = self.action_kit.format_as_markdown(opp, kit)
        html_report = self.action_kit.format_as_html(opp, kit)

        # Telegram: send condensed summary (first 3500 chars max)
        telegram_msg = md_summary[:3500]
        if len(md_summary) > 3500:
            telegram_msg += f"\n\n📧 _Full kit sent to your email ({len(md_summary)} chars)_"

        await self.telegram.send_text(telegram_msg)

        # Email: send full HTML report
        try:
            subject = f"🎬 Action Kit — {opp.get('title', '?')[:60]}"
            if hasattr(self.email, 'send_raw_html'):
                await self.email.send_raw_html(subject, html_report)
            else:
                # Fallback: use activity report
                await self.email.send_activity_report(
                    activity_type="action_kit",
                    opportunities=[opp],
                    extra_info={"action_kit_html": html_report, "opp_id": opp_id}
                )
        except Exception as e:
            logger.warning(f"Action kit email send failed: {e}")

        # Auto-move opportunity to 'researching' stage if still in 'discovered'
        current_stage = opp.get('pipeline_stage') or 'discovered'
        if current_stage == 'discovered':
            self.kb.move_pipeline_stage(
                opp_id, 'researching',
                append_note='Action kit generated — moved to researching'
            )

        logger.info(f"🎬 Action kit delivered for {opp_id}")
        return {"opportunity_id": opp_id, "kit": kit}

    # ─── External Signal Scanning ──────────────────────────

    async def run_signal_scan(self) -> dict:
        """Scan external sources (Google Jobs, Crunchbase) for early signals."""
        result = await self.signals.scan_all()
        total = sum(result.values())
        summary = self.signals.summary_for_telegram(days=7)
        await self.telegram.send_text(summary)
        logger.info(f"📡 Signal scan complete: {total} new signals")
        return result

    # ─── Claim Validation ─────────────────────────────────────

    async def _push_to_brain(self, opp: dict):
        """Push opportunity to Open Brain knowledge graph.

        Idempotent + safe: silently skips if brain not configured or fails.
        Called for every FIRE and HIGH alert across all discovery motors.
        """
        try:
            if self.brain and opp.get('tier') in ('FIRE', 'HIGH', 'VAY'):
                await self.brain.push_opportunity(opp)
        except Exception as e:
            logger.debug(f"Brain push skipped: {e}")

    async def _send_high_alert_with_brain(self, opp: dict):
        """HIGH alert + Open Brain push (lightweight version of FIRE pipeline).

        Used across all motors. HIGH tier gets Brain push but skips the
        expensive pattern/wow/validation pipeline (FIRE-only).
        """
        await self._push_to_brain(opp)
        await self.telegram.send_high_alert(opp)

    async def _send_fire_alert_with_validation(self, opp: dict):
        """Full Wildcatter pipeline before FIRE alert:

            Pattern envanteri (7 pattern) →
            Wow threshold (5 kriter, if FIRE + patterns strong) →
            Verifiability (Hassabis insight) →
            Claim validation (Haiku + web search) →
            Consensus scoring (Gemini Flash blind) →
            Open Brain push (knowledge graph, FIRE/HIGH/VAY only)

        If Wow threshold passes → VAY tier (sends special 🌟 alert instead of 🔥)
        Idempotent: skips pattern/wow if already computed (e.g. Mode 2 pre-computed).
        """
        badges = []
        opp_id = opp.get('id')

        # 1. Pattern Envanteri Filter (7 pattern) — idempotent
        pattern_result = None
        # Check if pattern already computed (Mode 2 does this inline)
        existing_pattern = opp.get('pattern_matches_json')
        if existing_pattern:
            # Parse if it's a string (from DB)
            import json as _json
            try:
                pattern_result = (_json.loads(existing_pattern)
                                  if isinstance(existing_pattern, str)
                                  else existing_pattern)
                badges.append(self.patterns.format_summary(pattern_result))
            except Exception:
                pattern_result = None

        if not pattern_result:
            try:
                pattern_result = self.patterns.match_and_save(opp_id, opp) if opp_id \
                                  else self.patterns.match(opp)
                badges.append(self.patterns.format_summary(pattern_result))
                # Store back on opp for wow threshold access
                opp['pattern_matches_json'] = pattern_result
                opp['pattern_count'] = pattern_result.get('count', 0)
            except Exception as e:
                logger.warning(f"Pattern match skipped for {opp_id}: {e}")
                badges.append("○ patterns N/A")

        # 2. Wow Threshold — only if patterns are strong enough
        # Idempotent: skip if already computed
        is_vay = bool(opp.get('is_vay') or opp.get('_is_vay'))
        wow_result = None
        existing_wow = opp.get('wow_json')
        if existing_wow and not wow_result:
            import json as _json
            try:
                wow_result = (_json.loads(existing_wow)
                              if isinstance(existing_wow, str)
                              else existing_wow)
                badges.append(self.wow.format_badge(wow_result))
                if wow_result.get('verdict') == 'VAY':
                    is_vay = True
            except Exception:
                wow_result = None

        if not wow_result and pattern_result and pattern_result.get('verdict') in ('wow_candidate', 'high_match'):
            try:
                wow_result = self.wow.evaluate_and_save(opp_id, opp) if opp_id \
                              else self.wow.evaluate(opp)
                badges.append(self.wow.format_badge(wow_result))
                if wow_result.get('verdict') == 'VAY':
                    is_vay = True
                    logger.info(f"🌟 VAY tier opportunity: {opp_id}")
            except Exception as e:
                logger.warning(f"Wow eval skipped for {opp_id}: {e}")

        # 3. Claim Validation (Haiku + web search, includes verifiability score)
        validation_result = None
        try:
            validation_result = self.validator.validate(opp)
            badges.append(self.validator.format_badge(validation_result))
            if validation_result.get('status') == 'disputed':
                logger.warning(f"🔎 DISPUTED CLAIMS in {opp_id}")
            # VAY tier requires verifiability_score ≥ 8
            verif_score = validation_result.get('verifiability_score', 5)
            if is_vay and verif_score < 8:
                logger.warning(
                    f"🌟 {opp_id} was VAY candidate but verifiability={verif_score}/10 "
                    f"(min 8 required) — downgraded to FIRE"
                )
                is_vay = False
        except Exception as e:
            logger.warning(f"Validation skipped for {opp_id}: {e}")
            badges.append("❓ not validated")

        # 4. Consensus check (Gemini Flash blind re-score)
        try:
            consensus = self.consensus.check_consensus(opp)
            badges.append(self.consensus.format_badge(consensus))
        except Exception as e:
            logger.warning(f"Consensus skipped for {opp_id}: {e}")
            badges.append("⚪ consensus N/A")

        # Attach validation badge
        opp['_validation_badge'] = " · ".join(badges)

        # Push to Open Brain (knowledge graph, semantic search)
        await self._push_to_brain(opp)

        # Send the right alert type
        if is_vay:
            # Override tier to VAY for alert rendering
            opp['tier'] = 'VAY'
            opp['_is_vay'] = True
            await self.telegram.send_fire_alert(opp)  # Same method, will check _is_vay flag
        else:
            await self.telegram.send_fire_alert(opp)

    async def run_pattern_match(self, opp_id: str) -> dict:
        """Evaluate Fatih's 7 pattern inventory for an opportunity."""
        cursor = self.kb.conn.cursor()
        cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
        row = cursor.fetchone()
        if not row:
            await self.telegram.send_text(f"❌ `{opp_id}` not found.")
            return {"error": "not_found"}
        opp = dict(row)

        try:
            result = self.patterns.match_and_save(opp_id, opp)
        except Exception as e:
            logger.error(f"Pattern match failed: {e}")
            await self.telegram.send_text(f"❌ Pattern match failed: {e}")
            return {"error": str(e)}

        msg = f"🧬 *Pattern Envanteri — {opp.get('title', '?')[:60]}*\n"
        msg += f"`{opp_id}`\n\n"
        msg += self.patterns.format_full(result)
        await self.telegram.send_text(msg)
        return {"opportunity_id": opp_id, "patterns": result}

    async def run_wow_eval(self, opp_id: str) -> dict:
        """Evaluate 5-criterion Vay (Wow) threshold for an opportunity."""
        cursor = self.kb.conn.cursor()
        cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
        row = cursor.fetchone()
        if not row:
            await self.telegram.send_text(f"❌ `{opp_id}` not found.")
            return {"error": "not_found"}
        opp = dict(row)

        # Ensure pattern match exists first
        if not opp.get('pattern_matches_json'):
            try:
                self.patterns.match_and_save(opp_id, opp)
                # Reload
                cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
                opp = dict(cursor.fetchone())
            except Exception as e:
                logger.warning(f"Pattern prerequisite failed: {e}")

        try:
            result = self.wow.evaluate_and_save(opp_id, opp)
        except Exception as e:
            logger.error(f"Wow eval failed: {e}")
            await self.telegram.send_text(f"❌ Wow eval failed: {e}")
            return {"error": str(e)}

        msg = f"🌟 *Vay Eşiği — {opp.get('title', '?')[:60]}*\n"
        msg += f"`{opp_id}`\n\n"
        msg += self.wow.format_full(result)
        await self.telegram.send_text(msg)
        return {"opportunity_id": opp_id, "wow": result}

    # ─── Wildcatter Family Scanners ────────────────────────

    async def run_family5(self) -> dict:
        """Weekly cost curves scan (Aile 5)."""
        result = self.family5.scan_weekly()
        signals = result.get('signals', [])
        correlations = result.get('correlations', [])
        try:
            if signals or correlations:
                lines = [f"💰 *Cost Curves Scan — {len(signals)} signal*"]
                for s in signals[:5]:
                    lines.append(f"  • {s.get('headline', '?')}")
                for c in correlations:
                    lines.append(f"  🔗 {c.get('name')}: {c.get('implication', '')}")
                await self.telegram.send_text("\n".join(lines))
            else:
                logger.info("💰 No cost signals this week")
        except Exception as e:
            logger.warning(f"Cost curves telegram failed: {e}")
        return result

    async def run_family1(self) -> dict:
        """Weekly science & patent scan (Aile 1)."""
        result = self.family1.scan_weekly()
        total = result.get('total_findings', 0)
        try:
            by_cat = result.get('by_category', {})
            summary = (
                f"🔬 *Science & Patent Scan*\n"
                f"{total} new findings this week:\n"
            )
            for cat, cnt in by_cat.items():
                if cnt > 0:
                    summary += f"  • {cat}: {cnt}\n"
            await self.telegram.send_text(summary)
        except Exception as e:
            logger.warning(f"Science telegram failed: {e}")
        return result

    async def run_family2(self) -> dict:
        """Weekly infrastructure launch scan (Aile 2)."""
        result = self.family2.scan_weekly()
        total = result.get('total_launches', 0)
        try:
            if total > 0:
                lines = [f"🔌 *Infra Launches — {total} new primitives*"]
                for launch in result.get('launches', [])[:5]:
                    name = launch.get('primitive_name', '?')
                    src = launch.get('source_name', '?')
                    unlocks = launch.get('what_unlocks', '')[:100]
                    lines.append(f"  • {name} ({src})")
                    if unlocks:
                        lines.append(f"    _{unlocks}_")
                await self.telegram.send_text("\n".join(lines))
        except Exception as e:
            logger.warning(f"Infra telegram failed: {e}")
        return result

    async def run_scorer_audit(self) -> dict:
        """Monthly scorer drift audit."""
        result = self.scorer_audit.run_monthly_audit()
        try:
            if result.get('status') == 'complete':
                drift = result.get('drift_detected', False)
                verdict = result.get('verdict', '')
                icon = '⚠️' if drift else '✅'
                msg = (
                    f"🔎 *Scorer Audit — {result.get('month', '?')}*\n"
                    f"{icon} Drift: {'DETECTED' if drift else 'Clean'}\n\n"
                    f"{verdict}\n"
                )
                if drift and result.get('recommendations'):
                    msg += "\n*Öneriler:*\n"
                    for r in result['recommendations'][:3]:
                        msg += f"  • {r}\n"
                await self.telegram.send_text(msg)
        except Exception as e:
            logger.warning(f"Audit telegram failed: {e}")
        return result

    async def run_layer_a(self) -> dict:
        """Generate weekly Layer A — Dünya Tomografisi."""
        report = self.layers.generate_layer_a()
        # Email
        try:
            subject = f"🌍 Tomografi — {report.get('week_label', '?')}"
            html = f"<pre style='font-family:sans-serif;white-space:pre-wrap'>{report.get('summary_md', '')}</pre>"
            if hasattr(self.email, 'send_raw_html'):
                await self.email.send_raw_html(subject, html)
        except Exception as e:
            logger.warning(f"Layer A email failed: {e}")
        # Telegram short
        try:
            items = len(report.get('items', []))
            await self.telegram.send_text(
                f"🌍 *Dünya Tomografisi — {report.get('week_label', '?')}*\n"
                f"{items} anomali gözlemlendi. Open Brain'e kaydedildi.\n"
                f"_Tam rapor email'de._"
            )
        except Exception as e:
            logger.warning(f"Layer A telegram failed: {e}")
        return report

    async def run_layer_b(self) -> dict:
        """Generate monthly Layer B — Konvergans Tezleri."""
        report = self.layers.generate_layer_b()
        try:
            subject = f"🧠 Konvergans Tezleri — {report.get('month_label', '?')}"
            html = f"<pre style='font-family:sans-serif;white-space:pre-wrap'>{report.get('summary_md', '')}</pre>"
            if hasattr(self.email, 'send_raw_html'):
                await self.email.send_raw_html(subject, html)
        except Exception as e:
            logger.warning(f"Layer B email failed: {e}")
        try:
            await self.telegram.send_text(
                f"🧠 *Konvergans Tezleri — {report.get('month_label', '?')}*\n"
                f"{len(report.get('theses', []))} tez. Email + Brain'e kaydedildi."
            )
        except Exception as e:
            logger.warning(f"Layer B telegram failed: {e}")
        return report

    async def run_layer_c(self) -> dict:
        """Generate quarterly Layer C — Aday Fırsatlar."""
        report = self.layers.generate_layer_c()
        try:
            # Layer C is pushed to Telegram fully (high-priority layer)
            summary = report.get('summary_md', '')[:3500]
            await self.telegram.send_text(summary)
        except Exception as e:
            logger.warning(f"Layer C telegram failed: {e}")
        return report

    async def run_mode1(self, week_number: int = None) -> dict:
        """Execute Wildcatter Mod 1 (ThreadForge feed) weekly rotation."""
        logger.info("🎯 Running Wildcatter Mod 1 (ThreadForge feed)...")
        report = self.mode1.run_weekly(week_number=week_number)

        # Email summary
        try:
            subject = f"🎯 ThreadForge Feed — Week {report.get('week_label', '?')}"
            summary = report.get('summary_md', '')
            if hasattr(self.email, 'send_raw_html'):
                # Minimal markdown→html
                html = f"<pre style='font-family:sans-serif;white-space:pre-wrap'>{summary}</pre>"
                await self.email.send_raw_html(subject, html)
        except Exception as e:
            logger.warning(f"Mod 1 email failed: {e}")

        # Telegram short summary
        try:
            task_count = report.get('tasks_run', 0)
            total_findings = sum(
                len(t.get('findings', []))
                for t in report.get('task_results', [])
                if not t.get('error')
            )
            short = (
                f"🎯 *ThreadForge Feed — Week {report.get('week_label', '?')}*\n"
                f"{task_count} task koştu, {total_findings} bulgu. "
                f"Email'e tam rapor gönderildi."
            )
            await self.telegram.send_text(short)
        except Exception as e:
            logger.warning(f"Mod 1 telegram failed: {e}")

        logger.info(f"🎯 Mod 1 complete: {report.get('tasks_run', 0)} tasks")
        return report

    async def run_mode2(self, num_searches: int = 3) -> dict:
        """Execute Wildcatter Mod 2 (sector-agnostic unicorn hunt)."""
        logger.info("🦄 Running Wildcatter Mod 2 (unicorn hunt)...")
        result = self.mode2.run(num_searches=num_searches)

        opportunities = result.get('opportunities', [])
        vay_count = result.get('vay_count', 0)

        # Send VAY alerts — pass through validation pipeline (pattern/wow
        # are idempotent, so they won't re-run from Mode 2 pre-computation).
        # This adds verifiability + consensus badges to the alert.
        for opp in opportunities:
            if opp.get('is_vay'):
                opp['_is_vay'] = True
                try:
                    await self._send_fire_alert_with_validation(opp)
                except Exception as e:
                    logger.warning(f"VAY alert failed: {e}")

        # Telegram summary
        try:
            summary = (
                f"🦄 *Wildcatter Mod 2 — Unicorn Avı*\n\n"
                f"Raw candidates: {result.get('candidates_raw', 0)}\n"
                f"Construction filter sonrası: {result.get('candidates_filtered', 0)}\n"
                f"Değerlendirilen: {result.get('candidates_evaluated', 0)}\n"
                f"🌟 *VAY tier:* {vay_count}\n"
            )
            if vay_count == 0:
                summary += "\n_Bu aramada VAY fırsatı yok. Sistem standardı 'yıl asla boş' — yılda 3-5 hedef._"
            await self.telegram.send_text(summary)
        except Exception as e:
            logger.warning(f"Mod 2 summary failed: {e}")

        logger.info(f"🦄 Mod 2 complete: {vay_count} VAY / "
                    f"{result.get('candidates_evaluated', 0)} evaluated")
        return result

    async def run_consensus(self, opp_id: str) -> dict:
        """Manually trigger consensus check on an opportunity."""
        cursor = self.kb.conn.cursor()
        cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
        row = cursor.fetchone()
        if not row:
            await self.telegram.send_text(f"❌ `{opp_id}` not found.")
            return {"error": "not_found"}
        opp = dict(row)

        try:
            result = self.consensus.check_consensus(opp)
        except Exception as e:
            logger.error(f"Consensus failed: {e}")
            await self.telegram.send_text(f"❌ Consensus failed: {e}")
            return {"error": str(e)}

        msg = f"🧮 *Consensus — {opp.get('title', '?')[:60]}*\n"
        msg += f"`{opp_id}`\n\n"
        msg += self.consensus.format_full(result)
        await self.telegram.send_text(msg)

        return {"opportunity_id": opp_id, "consensus": result}

    async def run_validation(self, opp_id: str) -> dict:
        """Validate claims in an opportunity and deliver result via Telegram."""
        logger.info(f"🔎 Validating claims for {opp_id}...")

        cursor = self.kb.conn.cursor()
        cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
        row = cursor.fetchone()
        if not row:
            await self.telegram.send_text(f"❌ Opportunity `{opp_id}` not found.")
            return {"error": "not_found"}
        opp = dict(row)

        try:
            result = self.validator.validate(opp)
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            await self.telegram.send_text(f"❌ Validation failed: {e}")
            return {"error": str(e)}

        # Pretty summary for Telegram
        msg = f"🔎 *Validation — {opp.get('title', '?')[:60]}*\n"
        msg += f"`{opp_id}`\n\n"
        msg += self.validator.format_full(result)
        await self.telegram.send_text(msg)

        logger.info(
            f"🔎 Validation complete for {opp_id}: {result.get('status')} "
            f"(conf {result.get('confidence'):.2f})"
        )
        return {"opportunity_id": opp_id, "validation": result}

    # ─── Financial Modeling ──────────────────────────────────

    async def run_financial_model(self, opp_id: str) -> dict:
        """Generate a financial model for an opportunity and deliver via Telegram."""
        logger.info(f"💰 Running financial model for {opp_id}...")

        try:
            model = self.financial.model_opportunity(opp_id)
        except ValueError as e:
            await self.telegram.send_text(f"❌ {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Financial model failed: {e}")
            await self.telegram.send_text(f"❌ Financial model failed: {e}")
            return {"error": str(e)}

        # Fetch opp for rendering
        cursor = self.kb.conn.cursor()
        cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
        row = cursor.fetchone()
        opp = dict(row) if row else {'id': opp_id}

        summary = self.financial.format_summary(opp, model)
        await self.telegram.send_text(summary)

        logger.info(f"💰 Financial model delivered for {opp_id}")
        return {"opportunity_id": opp_id, "model": model}

    # ─── Capability Explorer ──────────────────────────────────

    async def run_exploration(self, capability: str = None,
                               industry: str = None,
                               count: int = 3) -> dict:
        """
        Run capability-first exploration.
        Starts from founder's skills, systematically explores adjacent industries.
        """
        logger.info("🔭 Running capability exploration...")

        if capability or industry:
            # Explore a specific intersection
            result = self.explorer.explore(capability=capability, industry=industry)
            results = [result] if result else []
        else:
            # Auto-select least explored capabilities
            explore_result = self.explorer.explore_multiple(count=count)
            results = explore_result.get('explorations', []) if isinstance(explore_result, dict) else explore_result

        opportunities = []
        for r in results:
            for opp in r.get('opportunities', []):
                opportunities.append(opp)
                tier = opp.get('tier', 'LOW')
                if tier == 'FIRE':
                    await self._send_fire_alert_with_validation(opp)
                elif tier == 'HIGH':
                    await self._send_high_alert_with_brain(opp)

                # Publish to event bus
                self.event_bus.publish('opportunity_scored', {
                    'id': opp.get('id'),
                    'title': opp.get('title'),
                    'tier': opp.get('tier'),
                    'sector': opp.get('sector'),
                    'weighted_total': opp.get('weighted_total'),
                    'tags': opp.get('tags', []),
                    'discovery_strategy': 'capability_explorer'
                }, source_module='capability_explorer')

            # Publish negative evidence if nothing found
            if r.get('negative_evidence'):
                self.event_bus.publish('negative_evidence', {
                    'capability': r.get('capability'),
                    'industry': r.get('industry'),
                    'message': r.get('negative_evidence')
                }, source_module='capability_explorer')

        if opportunities:
            summary = (
                f"🔭 CAPABILITY EXPLORATION COMPLETE\n\n"
                f"Explorations run: {len(results)}\n"
                f"Opportunities found: {len(opportunities)}\n"
            )
            for r in results:
                cap = r.get('capability', '?')
                ind = r.get('industry', '?')
                opp_count = len(r.get('opportunities', []))
                best = max((o.get('weighted_total', 0) for o in r.get('opportunities', [])), default=0)
                neg = "⚠️ negative evidence" if r.get('negative_evidence') else ""
                summary += f"\n  {cap} × {ind}: {opp_count} opps (best={best}) {neg}"

            await self.telegram.send_text(summary)

        # Send email report
        if opportunities:
            await self.email.send_activity_report(
                activity_type="explore",
                opportunities=opportunities,
                extra_info={
                    "explorations_run": len(results),
                    "capability": capability or "auto-selected",
                    "industry": industry or "auto-selected",
                }
            )

        logger.info(
            f"🔭 Capability exploration: {len(results)} explorations, "
            f"{len(opportunities)} opportunities"
        )
        return {
            'explorations': results,
            'opportunities': opportunities,
            'total_found': len(opportunities)
        }

    # ─── Temporal Intelligence ─────────────────────────────

    async def check_deadlines(self) -> dict:
        """Check regulatory deadlines and publish alerts."""
        logger.info("📅 Checking regulatory deadlines...")
        alerts = self.temporal.check_deadlines()

        if alerts:
            report = self.temporal.get_deadline_report()
            await self.telegram.send_text(report[:4000])

        return {'alerts': alerts, 'count': len(alerts)}

    # ─── Competitive Monitor ──────────────────────────────

    async def run_competitive_scan(self, opportunity_id: str = None) -> dict:
        """Run competitive intelligence scan."""
        logger.info("🏢 Running competitive scan...")

        result = self.competitors.scan_for_opportunity(opportunity_id)

        if result.get('signals_found', 0) > 0:
            report = self.competitors.get_competitor_report()
            await self.telegram.send_text(report[:4000])
        elif result.get('new_competitors_identified', 0) > 0:
            await self.telegram.send_text(
                f"🏢 Competitive scan complete:\n"
                f"New competitors identified: {result['new_competitors_identified']}\n"
                f"Competitors monitored: {result['competitors_monitored']}\n"
                f"Signals found: {result['signals_found']}"
            )

        return result

    # ─── Cross-Pollinator ─────────────────────────────────

    async def run_cross_pollination(self) -> dict:
        """Run cross-sector connection analysis."""
        logger.info("🔗 Running cross-pollination cycle...")

        result = self.crosspoll.run_cross_pollination()
        connections = result.get('connections', [])
        hybrids = result.get('hybrid_opportunities', [])

        # Send alerts for hybrid opportunities
        for opp in hybrids:
            tier = opp.get('tier', 'LOW')
            if tier == 'FIRE':
                await self._send_fire_alert_with_validation(opp)
            elif tier == 'HIGH':
                await self._send_high_alert_with_brain(opp)

        if connections:
            summary = (
                f"🔗 CROSS-POLLINATION COMPLETE\n\n"
                f"Connections found: {len(connections)}\n"
                f"Hybrid opportunities: {len(hybrids)}\n"
            )
            for conn in connections[:5]:
                sectors = ', '.join(conn.get('sectors', []))
                summary += (
                    f"\n• [{conn.get('connection_type', '?')}] "
                    f"{sectors}: {conn.get('insight', '')[:100]}"
                )
            await self.telegram.send_text(summary)

        # Email report
        if hybrids:
            await self.email.send_activity_report(
                activity_type="crosspoll",
                opportunities=hybrids,
                extra_info={
                    "connections_found": len(connections),
                    "hybrid_opportunities": len(hybrids),
                }
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
