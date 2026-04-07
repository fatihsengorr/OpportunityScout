"""
OpportunityScout — Telegram Bot

Handles all output to the operator via Telegram:
- Instant alerts for FIRE opportunities
- Daily intelligence digests
- Weekly strategic reports
- Interactive commands (/portfolio, /deep_dive, /feedback, etc.)
"""

import asyncio
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger("scout.telegram")

# Try to import telegram library
try:
    from telegram import Bot, Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    logger.warning("python-telegram-bot not installed. Install with: pip install python-telegram-bot")


class TelegramNotifier:
    """
    Sends notifications and reports via Telegram.
    Also handles incoming commands from the operator.
    """

    def __init__(self, config: dict):
        self.config = config
        tg_config = config.get('telegram', {})
        self.bot_token = tg_config.get('bot_token') or os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = tg_config.get('chat_id') or os.environ.get('TELEGRAM_CHAT_ID', '')
        self.alert_threshold = tg_config.get('instant_alert_threshold', 120)

        if HAS_TELEGRAM and self.bot_token:
            self.bot = Bot(token=self.bot_token)
        else:
            self.bot = None
            if not self.bot_token:
                logger.warning("Telegram bot token not configured")

    # ─── Alert Methods ──────────────────────────────────────

    async def send_fire_alert(self, opportunity: dict):
        """Send instant alert for a FIRE-tier opportunity."""
        scores = opportunity.get('scores', {})
        top_dims = self._escape_md(self._get_top_dimensions(scores, n=3))
        score_str = self._escape_md(str(opportunity.get('weighted_total', 0)))
        risks = self._escape_md(', '.join(opportunity.get('risks', ['N/A'])))
        opp_id = opportunity.get('id', 'N/A')

        message = (
            f"🔥 *FIRE OPPORTUNITY DETECTED*\n\n"
            f"*{self._escape_md(opportunity.get('title', 'Unknown'))}*\n\n"
            f"_{self._escape_md(opportunity.get('one_liner', ''))}_\n\n"
            f"📊 *Score: {score_str}/155*\n"
            f"🏆 Top: {top_dims}\n\n"
            f"⏰ *Why NOW:*\n{self._escape_md(opportunity.get('why_now', 'N/A'))}\n\n"
            f"🎯 *First Move:*\n{self._escape_md(opportunity.get('first_move', 'N/A'))}\n\n"
            f"💰 *Revenue Path:*\n{self._escape_md(opportunity.get('revenue_path', 'N/A'))}\n\n"
            f"⚠️ *Risks:* {risks}\n\n"
            f"{'⏰ *Action By:* ' + self._escape_md(opportunity.get('action_by', '')) + chr(10) + chr(10) if opportunity.get('action_by') else ''}"
            f"🔗 ID: `{self._escape_md(str(opp_id))}`\n"
            f"📎 /deep\\_dive\\_{self._escape_md(str(opp_id))}"
        )

        await self._send(message, parse_mode="MarkdownV2")

    async def send_high_alert(self, opportunity: dict):
        """Send alert for a HIGH-tier opportunity."""
        score_str = self._escape_md(str(opportunity.get('weighted_total', 0)))
        message = (
            f"⭐ *HIGH OPPORTUNITY*\n\n"
            f"*{self._escape_md(opportunity.get('title', 'Unknown'))}*\n"
            f"Score: {score_str}/155\n\n"
            f"_{self._escape_md(opportunity.get('one_liner', ''))}_\n\n"
            f"🎯 First Move: {self._escape_md(opportunity.get('first_move', 'N/A'))}\n\n"
            f"🔗 `{self._escape_md(str(opportunity.get('id', 'N/A')))}`"
        )
        await self._send(message, parse_mode="MarkdownV2")

    async def send_daily_digest(self, opportunities: list, signals: list,
                                 trends: list = None):
        """Send daily intelligence digest."""
        date_str = datetime.utcnow().strftime('%d %B %Y')

        # Header
        parts = [f"📊 *DAILY INTELLIGENCE BRIEF — {date_str}*\n"]

        # Top Opportunities
        if opportunities:
            parts.append("🏆 *TOP OPPORTUNITIES*")
            for i, opp in enumerate(opportunities[:5], 1):
                tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
                    opp.get('tier', ''), "📝"
                )
                score_str = self._escape_md(str(opp.get('weighted_total', 0)))
                parts.append(
                    f"{i}\\. {tier_emoji} *{self._escape_md(opp.get('title', 'Unknown'))}*\n"
                    f"   Score: {score_str} \\| "
                    f"{self._escape_md(opp.get('sector', 'N/A'))}\n"
                    f"   → _{self._escape_md(opp.get('one_liner', ''))}_"
                )
        else:
            parts.append("_No new opportunities above threshold today\\._")

        # Key Signals
        if signals:
            parts.append("\n📡 *KEY SIGNALS*")
            for signal in signals[:5]:
                parts.append(
                    f"• {self._escape_md(signal.get('summary', 'N/A'))}"
                )

        # Trends
        if trends:
            parts.append("\n📈 *TREND WATCH*")
            for trend in trends[:3]:
                parts.append(
                    f"• {self._escape_md(str(trend))}"
                )

        message = "\n".join(parts)
        await self._send(message, parse_mode="MarkdownV2")

    async def send_weekly_report(self, report_data: dict):
        """Send comprehensive weekly strategic report."""
        date_str = datetime.utcnow().strftime('%d %B %Y')

        parts = [f"📋 *WEEKLY STRATEGY REPORT — Week of {date_str}*\n"]

        # Executive Summary
        summary = report_data.get('summary', 'No summary available.')
        parts.append(f"*EXECUTIVE SUMMARY*\n{self._escape_md(summary)}\n")

        # Stats
        stats = report_data.get('stats', {})
        parts.append(
            f"📊 *STATS*\n"
            f"• New opportunities: {self._escape_md(str(stats.get('new_opportunities', 0)))}\n"
            f"• Fire alerts: {self._escape_md(str(stats.get('fire_count', 0)))}\n"
            f"• Sources scanned: {self._escape_md(str(stats.get('sources_scanned', 0)))}\n"
            f"• Avg score: {self._escape_md(str(stats.get('avg_score', 0)))}"
        )

        # Top opportunities this week
        opps = report_data.get('top_opportunities', [])
        if opps:
            parts.append("\n🏆 *TOP OPPORTUNITIES THIS WEEK*")
            for opp in opps[:10]:
                parts.append(
                    f"• {self._escape_md(str(opp.get('tier', '?')))} "
                    f"{self._escape_md(opp.get('title', 'Unknown'))} "
                    f"— Score: {self._escape_md(str(opp.get('weighted_total', 0)))}"
                )

        # Evolution log
        evolutions = report_data.get('evolutions', [])
        if evolutions:
            parts.append("\n🔄 *SELF\\-IMPROVEMENT LOG*")
            for evo in evolutions[:5]:
                parts.append(f"• {self._escape_md(str(evo))}")

        # Recommended actions
        actions = report_data.get('recommended_actions', [])
        if actions:
            parts.append("\n🎯 *RECOMMENDED ACTIONS*")
            for i, action in enumerate(actions[:5], 1):
                parts.append(f"{i}\\. {self._escape_md(str(action))}")

        message = "\n".join(parts)

        # Split if too long for Telegram (4096 char limit)
        if len(message) > 4000:
            # Send in chunks
            chunks = self._split_message(message, 4000)
            for chunk in chunks:
                await self._send(chunk, parse_mode="MarkdownV2")
        else:
            await self._send(message, parse_mode="MarkdownV2")

    async def send_evolution_notification(self, changes: list):
        """Notify operator about self-improvement changes."""
        parts = ["🧬 *SCOUT EVOLUTION UPDATE*\n"]
        for change in changes:
            parts.append(f"• {self._escape_md(str(change))}")
        
        message = "\n".join(parts)
        await self._send(message, parse_mode="MarkdownV2")

    async def send_text(self, text: str):
        """Send a plain text message (no formatting)."""
        await self._send(text)

    # ─── Interactive Command Handlers ───────────────────────

    def setup_command_handlers(self, scout_engine):
        """
        Set up Telegram command handlers for interactive use.
        Must be called with a reference to the ScoutEngine.
        Returns an Application that can be run.
        """
        if not HAS_TELEGRAM or not self.bot_token:
            logger.warning("Cannot set up command handlers without telegram library and token")
            return None

        app = Application.builder().token(self.bot_token).build()

        async def cmd_scout(update: Update, context):
            args = context.args
            mode = args[0].lower() if args else '1'

            if mode == 'all':
                await update.message.reply_text(
                    "🔍 Starting FULL scan (all 3 tiers)... 15-20 minutes.\n"
                    "📧 Comprehensive report will be emailed when done."
                )
                result = await scout_engine.run_full_scan(tiers=[1, 2, 3])
                combined = result.get('combined_stats', {})
                duration = result.get('total_duration', 0)
                minutes = int(duration // 60)
                await update.message.reply_text(
                    f"✅ Full scan complete (Tier 1+2+3)!\n"
                    f"• Total opportunities: {combined.get('opportunities_found', 0)}\n"
                    f"• FIRE: {combined.get('fire_alerts', 0)} | HIGH: {combined.get('high_alerts', 0)}\n"
                    f"• Duration: {minutes}m\n"
                    f"📧 Detailed report sent to email!"
                )
            elif mode in ('1', '2', '3'):
                await update.message.reply_text(
                    f"🔍 Starting Tier {mode} scan... This may take a few minutes."
                )
                result = await scout_engine.run_scan_cycle(tier=int(mode))
                await update.message.reply_text(
                    f"✅ Tier {mode} scan complete!\n"
                    f"• Sources scanned: {result.get('sources_scanned', 0)}\n"
                    f"• Opportunities found: {result.get('opportunities_found', 0)}\n"
                    f"• Signals detected: {result.get('signals_found', 0)}\n"
                    f"• Fire alerts: {result.get('fire_alerts', 0)}"
                )
            else:
                await update.message.reply_text(
                    "Usage: /scout [1|2|3|all]\nDefault: Tier 1"
                )
                return

        async def cmd_portfolio(update: Update, context):
            opps = scout_engine.kb.get_top_opportunities(limit=10)
            if not opps:
                await update.message.reply_text("📭 No opportunities in portfolio yet.")
                return

            for i, opp in enumerate(opps, 1):
                tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
                    opp.get('tier', ''), "📝"
                )
                score = opp.get('weighted_total', 0)
                title = opp.get('title', '?')
                one_liner = opp.get('one_liner', '')
                sector = opp.get('sector', 'N/A')
                first_move = opp.get('first_move', 'N/A')
                revenue = opp.get('revenue_path', 'N/A')
                why_now = opp.get('why_now', '')
                risks = json.loads(opp.get('risks_json', '[]')) if opp.get('risks_json') else []
                risk_str = ', '.join(risks[:3]) if risks else 'N/A'

                why_line = f"⏰ Why NOW: {why_now}\n\n" if why_now else ""
                msg = (
                    f"{tier_emoji} #{i} — {title}\n"
                    f"📊 Score: {score}/155 | Sector: {sector}\n\n"
                    f"💡 {one_liner}\n\n"
                    f"{why_line}"
                    f"🎯 First Move: {first_move}\n\n"
                    f"💰 Revenue: {revenue}\n\n"
                    f"⚠️ Risks: {risk_str}"
                )
                await update.message.reply_text(msg)
                await asyncio.sleep(0.5)  # avoid rate limiting

        async def cmd_stats(update: Update, context):
            stats = scout_engine.kb.get_stats()
            msg = (
                f"📈 *SCOUT STATISTICS*\n\n"
                f"Total Opportunities: {stats.get('total_opportunities', 0)}\n"
                f"  🔥 FIRE: {stats.get('fire_opportunities', 0)}\n"
                f"  ⭐ HIGH: {stats.get('high_opportunities', 0)}\n"
                f"Total Signals: {stats.get('total_signals', 0)}\n"
                f"Total Scans: {stats.get('total_scans', 0)}\n"
                f"Evolutions: {stats.get('total_evolutions', 0)}\n"
                f"Avg Score: {stats.get('avg_score', 0)}"
            )
            await update.message.reply_text(msg)

        async def cmd_brain(update: Update, context):
            """Search Open Brain or show brain stats."""
            args = context.args
            if not args:
                # No args = show brain stats
                stats = await scout_engine.brain.get_brain_stats()
                if not stats:
                    await update.message.reply_text("❌ Open Brain not connected.")
                    return
                if isinstance(stats, str):
                    await update.message.reply_text(f"🧠 Open Brain Stats:\n\n{stats[:3000]}")
                else:
                    await update.message.reply_text(f"🧠 Open Brain Stats:\n\n{json.dumps(stats, indent=2, ensure_ascii=False)[:3000]}")
                return

            query = ' '.join(args)

            # Check for path filter: /brain intel:query or /brain projects:query
            path_filter = None
            if ':' in query and not query.startswith('http'):
                parts = query.split(':', 1)
                path_shortcuts = {
                    'intel': 'intelligence/',
                    'projects': 'projects/',
                    'context': 'context/',
                    'daily': 'daily/',
                    'skills': 'skills/',
                    'resources': 'resources/',
                }
                if parts[0].lower() in path_shortcuts:
                    path_filter = path_shortcuts[parts[0].lower()]
                    query = parts[1].strip()

            await update.message.reply_text(f"🧠 Searching Brain: \"{query}\"...")
            results = await scout_engine.brain.search_brain(query, path=path_filter, limit=5)

            if not results:
                await update.message.reply_text("🧠 No results found in Brain.")
                return

            if isinstance(results, str):
                await update.message.reply_text(f"🧠 Brain Results:\n\n{results[:3500]}")
                return

            if isinstance(results, list):
                for i, item in enumerate(results[:5], 1):
                    if isinstance(item, dict):
                        content = item.get('content', str(item))[:500]
                        path = item.get('path', '')
                        score = item.get('similarity', item.get('score', ''))
                        header = f"🧠 #{i}"
                        if path:
                            header += f" [{path}]"
                        if score:
                            header += f" ({score})"
                        await update.message.reply_text(f"{header}\n\n{content}")
                    else:
                        await update.message.reply_text(f"🧠 #{i}\n\n{str(item)[:500]}")
                    await asyncio.sleep(0.3)
            else:
                await update.message.reply_text(f"🧠 Brain Results:\n\n{str(results)[:3500]}")

        async def cmd_digest(update: Update, context):
            await update.message.reply_text("📊 Generating daily digest...")
            await scout_engine.generate_daily_digest()
            await update.message.reply_text("✅ Daily digest sent!")

        async def cmd_help(update: Update, context):
            msg = (
                "🤖 *OpportunityScout Commands*\n\n"
                "🔍 *Scanning*\n"
                "/scout — Tier 1 scan (default)\n"
                "/scout 2 — Specific tier scan\n"
                "/scout all — Full scan (Tier 1+2+3)\n\n"
                "🎲 *Discovery*\n"
                "/serendipity — Broad cross-sector discovery\n"
                "/serendipity deep — Deep Opus-powered analysis\n"
                "/localize — Samwer lens: copy proven models\n"
                "/localize [sector] — Focus (e.g. /localize proptech)\n"
                "/generate — Generate novel business models\n"
                "/generate [focus] — Focus area (e.g. /generate scan-to-bim)\n"
                "/explore — Capability-first exploration (auto)\n"
                "/explore [cap] — Explore specific capability\n"
                "/explore [cap] [industry] — Explore intersection\n"
                "/crosspoll — Cross-sector connections\n"
                "/deadlines — Regulatory deadline tracker\n"
                "/competitors — Competitive intelligence\n"
                "/competitors [OPP-ID] — Analyze specific opportunity\n\n"
                "🧠 *Open Brain*\n"
                "/brain — Brain stats overview\n"
                "/brain [query] — Search Brain semantically\n"
                "  Path filters: intel: projects: context: daily: skills: resources:\n"
                "  e.g. /brain intel:construction AI\n\n"
                "📊 *Reports*\n"
                "/portfolio — View top 10 opportunities\n"
                "/stats — System statistics\n"
                "/digest — Generate today's digest\n"
                "/help — Show this message"
            )
            await update.message.reply_text(msg)

        async def cmd_generate(update: Update, context):
            focus = ' '.join(context.args) if context.args else None
            msg = "💡 Generating business models"
            if focus:
                msg += f" (focus: {focus})"
            msg += "... This takes 3-5 minutes."
            await update.message.reply_text(msg)
            result = await scout_engine.generate_business_models(
                focus_area=focus, count=3
            )
            models = result.get('models', [])
            if models:
                await update.message.reply_text(
                    f"✅ Generated {len(models)} business models! "
                    f"Check above for details."
                )
            else:
                await update.message.reply_text(
                    "❌ No models generated. Need more accumulated scan data."
                )

        async def cmd_serendipity(update: Update, context):
            mode = context.args[0] if context.args else 'daily'
            if mode == 'deep':
                await update.message.reply_text(
                    "🎲 Running DEEP serendipity scan (Opus, all sectors)... 5-8 min."
                )
                result = await scout_engine.run_serendipity_weekly()
            else:
                await update.message.reply_text(
                    "🎲 Running serendipity scan (broad sweep)... 2-3 min."
                )
                result = await scout_engine.run_serendipity_daily()

            passed = result.get('passed_filter', 0)
            await update.message.reply_text(
                f"🎲 Done! {result.get('raw_found', 0)} found, "
                f"{passed} passed founder fit filter."
            )

        async def cmd_localize(update: Update, context):
            focus = ' '.join(context.args) if context.args else None
            msg = "🌍 Running localization scan (Samwer lens)"
            if focus:
                msg += f" — focus: {focus}"
            msg += "... 5-8 min."
            await update.message.reply_text(msg)
            result = await scout_engine.run_localization_scan(
                focus_sector=focus, count=5
            )
            stored = result.get('opportunities_stored', 0)
            await update.message.reply_text(
                f"🌍 Done! {result.get('models_analyzed', 0)} models analyzed, "
                f"{stored} localization opportunities found."
            )

        async def cmd_explore(update: Update, context):
            args = context.args
            capability = None
            industry = None
            # Parse args: /explore or /explore it_infrastructure or /explore it_infrastructure managed_soc
            if args:
                capability = args[0]
                if len(args) > 1:
                    industry = args[1]

            msg = "🔭 Running capability exploration"
            if capability:
                msg += f" ({capability}"
                if industry:
                    msg += f" × {industry}"
                msg += ")"
            else:
                msg += " (auto-selecting least explored areas)"
            msg += "... 3-5 min."
            await update.message.reply_text(msg)

            result = await scout_engine.run_exploration(
                capability=capability, industry=industry, count=3
            )
            total = result.get('total_found', 0)
            explorations = result.get('explorations', [])
            await update.message.reply_text(
                f"🔭 Done! {len(explorations)} explorations, "
                f"{total} opportunities found."
            )

        app.add_handler(CommandHandler("scout", cmd_scout))
        app.add_handler(CommandHandler("portfolio", cmd_portfolio))
        app.add_handler(CommandHandler("stats", cmd_stats))
        app.add_handler(CommandHandler("generate", cmd_generate))
        app.add_handler(CommandHandler("serendipity", cmd_serendipity))
        app.add_handler(CommandHandler("localize", cmd_localize))
        app.add_handler(CommandHandler("explore", cmd_explore))

        async def cmd_deadlines(update: Update, context):
            await update.message.reply_text("📅 Checking regulatory deadlines...")
            result = await scout_engine.check_deadlines()
            report = scout_engine.temporal.get_deadline_report()
            # Split if too long
            if len(report) > 4000:
                report = report[:4000] + "\n..."
            await update.message.reply_text(report)

        async def cmd_competitors(update: Update, context):
            opp_id = context.args[0] if context.args else None
            msg = "🏢 Running competitive scan"
            if opp_id:
                msg += f" for {opp_id}"
            msg += "... 3-5 min."
            await update.message.reply_text(msg)
            result = await scout_engine.run_competitive_scan(opportunity_id=opp_id)
            await update.message.reply_text(
                f"🏢 Done! {result.get('new_competitors_identified', 0)} new competitors, "
                f"{result.get('signals_found', 0)} signals found."
            )

        async def cmd_crosspoll(update: Update, context):
            await update.message.reply_text(
                "🔗 Running cross-pollination analysis... 5-8 min."
            )
            result = await scout_engine.run_cross_pollination()
            connections = result.get('connections', [])
            hybrids = result.get('hybrid_opportunities', [])
            await update.message.reply_text(
                f"🔗 Done! {len(connections)} connections found, "
                f"{len(hybrids)} hybrid opportunities generated."
            )

        app.add_handler(CommandHandler("deadlines", cmd_deadlines))
        app.add_handler(CommandHandler("competitors", cmd_competitors))
        app.add_handler(CommandHandler("crosspoll", cmd_crosspoll))
        app.add_handler(CommandHandler("brain", cmd_brain))
        app.add_handler(CommandHandler("digest", cmd_digest))
        app.add_handler(CommandHandler("help", cmd_help))
        app.add_handler(CommandHandler("start", cmd_help))

        return app

    # ─── Internal Methods ───────────────────────────────────

    async def _send(self, text: str, parse_mode: str = None):
        """Send a message via Telegram bot."""
        if not self.bot or not self.chat_id:
            # Fallback: log to console
            logger.info(f"[TELEGRAM] {text}")
            return

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            # Retry without formatting
            if parse_mode:
                try:
                    clean = text.replace('*', '').replace('_', '').replace('\\', '')
                    await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=clean
                    )
                except Exception as e2:
                    logger.error(f"Telegram retry also failed: {e2}")

    @staticmethod
    def _escape_md(text: str) -> str:
        """Escape special characters for Telegram MarkdownV2."""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>',
                         '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    @staticmethod
    def _get_top_dimensions(scores: dict, n: int = 3) -> str:
        """Get the top N scoring dimensions as a string."""
        dim_scores = []
        for dim, data in scores.items():
            score = data.get('score', 0) if isinstance(data, dict) else data
            dim_scores.append((dim.replace('_', ' ').title(), score))
        dim_scores.sort(key=lambda x: x[1], reverse=True)
        return ", ".join([f"{d} {s}" for d, s in dim_scores[:n]])

    @staticmethod
    def _split_message(text: str, max_len: int) -> list:
        """Split a long message into chunks."""
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            # Find last newline before limit
            split_at = text.rfind('\n', 0, max_len)
            if split_at == -1:
                split_at = max_len
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip('\n')
        return chunks
