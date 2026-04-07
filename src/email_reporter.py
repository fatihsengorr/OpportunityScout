"""
OpportunityScout — Email Reporter (AWS SES)

Sends HTML-formatted reports via AWS SES:
- Daily intelligence digest
- Weekly strategic report
- FIRE/HIGH opportunity alerts
"""

import logging
import os
from datetime import datetime

logger = logging.getLogger("scout.email")

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
    logger.warning("boto3 not installed. Install with: pip install boto3")


class EmailReporter:
    """Sends HTML email reports via AWS SES API."""

    def __init__(self, config: dict):
        self.config = config
        email_config = config.get('email', {})
        self.from_email = email_config.get('from_email') or os.environ.get(
            'SES_FROM_EMAIL', '')
        self.to_email = email_config.get('to_email') or os.environ.get(
            'SES_TO_EMAIL', '')
        self.region = email_config.get('ses_region') or os.environ.get(
            'SES_REGION', 'eu-central-1')

        aws_key = os.environ.get('AWS_ACCESS_KEY_ID', '')
        aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY', '')

        self.enabled = bool(HAS_BOTO3 and self.from_email and self.to_email and aws_key)

        if self.enabled:
            self.ses_client = boto3.client(
                'ses',
                region_name=self.region,
                aws_access_key_id=aws_key,
                aws_secret_access_key=aws_secret
            )
        else:
            self.ses_client = None
            if not HAS_BOTO3:
                logger.warning("Email reporter disabled: boto3 not installed")
            elif not self.from_email or not self.to_email:
                logger.warning("Email reporter disabled: SES_FROM_EMAIL or SES_TO_EMAIL not set")

    # ─── Report Methods ─────────────────────────────────────

    async def send_fire_alert(self, opportunity: dict):
        """Send FIRE opportunity alert email."""
        score = opportunity.get('weighted_total', 0)
        title = opportunity.get('title', 'Unknown')
        subject = f"🔥 FIRE OPPORTUNITY: {title} (Score: {score}/155)"

        html = self._render_opportunity_detail(opportunity, is_fire=True)
        self._send(subject, html)

    async def send_high_alert(self, opportunity: dict):
        """Send HIGH opportunity alert email."""
        score = opportunity.get('weighted_total', 0)
        title = opportunity.get('title', 'Unknown')
        subject = f"⭐ HIGH OPPORTUNITY: {title} (Score: {score}/155)"

        html = self._render_opportunity_detail(opportunity, is_fire=False)
        self._send(subject, html)

    async def send_daily_digest(self, opportunities: list, signals: list,
                                 trends: list = None):
        """Send daily intelligence digest as HTML email."""
        date_str = datetime.utcnow().strftime('%d %B %Y')
        subject = f"📊 OpportunityScout Daily Brief — {date_str}"

        html = self._render_daily_digest(opportunities, signals, trends, date_str)
        self._send(subject, html)

    async def send_weekly_report(self, report_data: dict):
        """Send weekly strategic report as HTML email."""
        date_str = datetime.utcnow().strftime('%d %B %Y')
        subject = f"📋 OpportunityScout Weekly Report — {date_str}"

        html = self._render_weekly_report(report_data, date_str)
        self._send(subject, html)

    async def send_activity_report(self, activity_type: str, opportunities: list,
                                      extra_info: dict = None):
        """Send a report email after any discovery activity (serendipity, localize, generate)."""
        date_str = datetime.utcnow().strftime('%d %B %Y %H:%M UTC')
        extra = extra_info or {}

        emoji_map = {
            "serendipity": "🎲",
            "serendipity_deep": "🎲",
            "localize": "🌍",
            "generate": "💡",
        }
        title_map = {
            "serendipity": "Serendipity Daily Scan",
            "serendipity_deep": "Serendipity Deep Scan (Opus)",
            "localize": "Localization Scan (Samwer Lens)",
            "generate": "Business Model Generation",
        }

        emoji = emoji_map.get(activity_type, "📡")
        title = extra.get('scan_type') or title_map.get(activity_type, activity_type)
        subject = f"{emoji} {title} — {len(opportunities)} opportunities — {date_str}"

        # Sort by score
        sorted_opps = sorted(
            opportunities,
            key=lambda x: x.get('weighted_total', 0),
            reverse=True
        )[:20]

        # Build opportunity cards
        opp_cards = ""
        for i, opp in enumerate(sorted_opps, 1):
            tier = opp.get('tier', '')
            tier_emoji = {'FIRE': '🔥', 'HIGH': '⭐', 'MEDIUM': '📊'}.get(tier, '📝')
            score = opp.get('weighted_total', 0)
            border_color = {'FIRE': '#dc2626', 'HIGH': '#f59e0b', 'MEDIUM': '#3b82f6'}.get(tier, '#9ca3af')
            badge_bg = {'FIRE': '#fef2f2', 'HIGH': '#fffbeb', 'MEDIUM': '#eff6ff'}.get(tier, '#f9fafb')
            badge_color = {'FIRE': '#dc2626', 'HIGH': '#d97706', 'MEDIUM': '#2563eb'}.get(tier, '#6b7280')

            discovery = opp.get('discovery_path', '')
            discovery_line = f'<div style="color:#7c3aed;font-size:13px;margin-top:6px;">💡 {discovery[:150]}</div>' if discovery else ''

            opp_cards += f"""
            <div style="background:#ffffff;border:1px solid #e5e7eb;border-left:4px solid {border_color};border-radius:6px;padding:16px;margin-bottom:12px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
                    <div style="font-weight:700;font-size:15px;color:#111827;">
                        {tier_emoji} #{i} — {opp.get('title', '?')}
                    </div>
                    <div style="background:{badge_bg};color:{badge_color};padding:4px 12px;border-radius:12px;font-weight:700;font-size:13px;white-space:nowrap;margin-left:12px;">
                        {score}/155
                    </div>
                </div>
                <div style="color:#4b5563;font-size:14px;font-style:italic;margin-bottom:8px;">
                    {opp.get('one_liner', '')}
                </div>
                <table style="width:100%;font-size:13px;color:#374151;">
                    <tr>
                        <td style="padding:3px 0;"><strong>Sector:</strong> {opp.get('sector', 'N/A')}</td>
                        <td style="padding:3px 0;"><strong>Geography:</strong> {opp.get('geography', 'N/A')}</td>
                    </tr>
                    <tr><td colspan="2" style="padding:3px 0;"><strong>First Move:</strong> {opp.get('first_move', 'N/A')}</td></tr>
                    <tr><td colspan="2" style="padding:3px 0;"><strong>Revenue:</strong> {opp.get('revenue_path', 'N/A')}</td></tr>
                    {'<tr><td colspan="2" style="padding:3px 0;"><strong>⏰ Action By:</strong> <span style="color:#dc2626;font-weight:600;">' + opp.get('action_by') + '</span></td></tr>' if opp.get('action_by') else ''}
                </table>
                {discovery_line}
                <div style="margin-top:6px;font-size:11px;color:#9ca3af;">ID: {opp.get('id', 'N/A')}</div>
            </div>"""

        # Extra info section
        extra_section = ""
        if extra:
            extra_items = ""
            for k, v in extra.items():
                extra_items += f"<li><strong>{k}:</strong> {v}</li>"
            extra_section = f'<ul style="color:#374151;font-size:14px;">{extra_items}</ul>'

        # Tier distribution
        tier_dist = {'FIRE': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        for opp in opportunities:
            t = opp.get('tier', 'LOW')
            tier_dist[t] = tier_dist.get(t, 0) + 1

        gradient = {
            "serendipity": "linear-gradient(135deg,#4c1d95,#7c3aed)",
            "serendipity_deep": "linear-gradient(135deg,#4c1d95,#7c3aed)",
            "localize": "linear-gradient(135deg,#065f46,#059669)",
            "generate": "linear-gradient(135deg,#92400e,#d97706)",
        }.get(activity_type, "linear-gradient(135deg,#0f172a,#1e40af)")

        html = f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:750px;margin:0 auto;background:#ffffff;">
            <div style="background:{gradient};padding:28px;border-radius:8px 8px 0 0;">
                <h1 style="color:white;margin:0;font-size:22px;">{emoji} {title}</h1>
                <p style="color:rgba(255,255,255,0.7);margin:8px 0 0;font-size:14px;">{date_str}</p>
            </div>
            <div style="padding:24px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;">

                <div style="display:flex;gap:12px;margin-bottom:24px;">
                    <div style="flex:1;background:#f0fdf4;padding:14px;border-radius:8px;text-align:center;">
                        <div style="font-size:28px;font-weight:bold;color:#16a34a;">{len(opportunities)}</div>
                        <div style="color:#6b7280;font-size:11px;">Found</div>
                    </div>
                    <div style="flex:1;background:#fef2f2;padding:14px;border-radius:8px;text-align:center;">
                        <div style="font-size:28px;font-weight:bold;color:#dc2626;">{tier_dist.get('FIRE', 0)}</div>
                        <div style="color:#6b7280;font-size:11px;">FIRE</div>
                    </div>
                    <div style="flex:1;background:#fffbeb;padding:14px;border-radius:8px;text-align:center;">
                        <div style="font-size:28px;font-weight:bold;color:#d97706;">{tier_dist.get('HIGH', 0)}</div>
                        <div style="color:#6b7280;font-size:11px;">HIGH</div>
                    </div>
                    <div style="flex:1;background:#eff6ff;padding:14px;border-radius:8px;text-align:center;">
                        <div style="font-size:28px;font-weight:bold;color:#2563eb;">{tier_dist.get('MEDIUM', 0)}</div>
                        <div style="color:#6b7280;font-size:11px;">MEDIUM</div>
                    </div>
                </div>

                {extra_section}

                <h2 style="margin:0 0 16px;font-size:16px;color:#111827;">🏆 Top Opportunities</h2>
                {opp_cards if opp_cards else '<p style="color:#6b7280;">No opportunities found.</p>'}

                <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0 16px;">
                <p style="color:#9ca3af;font-size:12px;margin:0;text-align:center;">
                    OpportunityScout • {title} • {date_str}
                </p>
            </div>
        </div>"""

        self._send(subject, html)

    async def send_scan_report(self, scan_results: dict, all_opportunities: list):
        """Send comprehensive scan completion report email."""
        date_str = datetime.utcnow().strftime('%d %B %Y %H:%M UTC')
        tiers_scanned = scan_results.get('tiers_scanned', [1])
        tier_label = '+'.join(str(t) for t in tiers_scanned)

        subject = (
            f"📡 OpportunityScout Scan Report (Tier {tier_label}) — "
            f"{len(all_opportunities)} opportunities"
        )

        html = self._render_scan_report(scan_results, all_opportunities, date_str, tier_label)
        self._send(subject, html)

    # ─── HTML Renderers ─────────────────────────────────────

    def _render_opportunity_detail(self, opp: dict, is_fire: bool = False) -> str:
        """Render a single opportunity as detailed HTML."""
        scores = opp.get('scores', {})
        score_rows = ""
        for dim, data in scores.items():
            score_val = data.get('score', 0) if isinstance(data, dict) else data
            reason = data.get('reason', '') if isinstance(data, dict) else ''
            dim_name = dim.replace('_', ' ').title()
            bar_width = score_val * 10
            color = '#22c55e' if score_val >= 8 else '#eab308' if score_val >= 5 else '#ef4444'
            score_rows += f"""
            <tr>
                <td style="padding:6px 12px;font-weight:500;">{dim_name}</td>
                <td style="padding:6px 12px;text-align:center;font-weight:bold;">{score_val}/10</td>
                <td style="padding:6px 12px;">
                    <div style="background:#e5e7eb;border-radius:4px;height:8px;width:100px;">
                        <div style="background:{color};border-radius:4px;height:8px;width:{bar_width}px;"></div>
                    </div>
                </td>
                <td style="padding:6px 12px;color:#6b7280;font-size:13px;">{reason}</td>
            </tr>"""

        risks = opp.get('risks', [])
        risk_items = ''.join(f'<li style="margin:4px 0;">{r}</li>' for r in risks)

        accent = '#dc2626' if is_fire else '#f59e0b'
        badge = '🔥 FIRE' if is_fire else '⭐ HIGH'

        return f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:700px;margin:0 auto;background:#ffffff;">
            <div style="background:{accent};padding:20px 24px;border-radius:8px 8px 0 0;">
                <h1 style="color:white;margin:0;font-size:20px;">{badge} OPPORTUNITY DETECTED</h1>
            </div>
            <div style="padding:24px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;">
                <h2 style="margin:0 0 8px;color:#111827;">{opp.get('title', 'Unknown')}</h2>
                <p style="color:#6b7280;margin:0 0 16px;font-size:15px;font-style:italic;">{opp.get('one_liner', '')}</p>

                <div style="display:flex;gap:16px;margin-bottom:20px;">
                    <div style="background:#f3f4f6;padding:12px 20px;border-radius:8px;text-align:center;">
                        <div style="font-size:28px;font-weight:bold;color:{accent};">{opp.get('weighted_total', 0)}</div>
                        <div style="color:#6b7280;font-size:12px;">/ 185 points</div>
                    </div>
                    <div style="background:#f3f4f6;padding:12px 20px;border-radius:8px;">
                        <div style="font-size:13px;color:#6b7280;">Sector</div>
                        <div style="font-weight:600;">{opp.get('sector', 'N/A')}</div>
                    </div>
                    <div style="background:#f3f4f6;padding:12px 20px;border-radius:8px;">
                        <div style="font-size:13px;color:#6b7280;">Geography</div>
                        <div style="font-weight:600;">{opp.get('geography', 'N/A')}</div>
                    </div>
                </div>

                <div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:12px 16px;margin-bottom:16px;border-radius:0 4px 4px 0;">
                    <strong>⏰ Why NOW:</strong><br>{opp.get('why_now', 'N/A')}
                </div>

                <div style="background:#dcfce7;border-left:4px solid #22c55e;padding:12px 16px;margin-bottom:16px;border-radius:0 4px 4px 0;">
                    <strong>🎯 First Move:</strong><br>{opp.get('first_move', 'N/A')}
                </div>

                <div style="background:#dbeafe;border-left:4px solid #3b82f6;padding:12px 16px;margin-bottom:16px;border-radius:0 4px 4px 0;">
                    <strong>💰 Revenue Path:</strong><br>{opp.get('revenue_path', 'N/A')}
                </div>

                <h3 style="margin:20px 0 8px;color:#111827;">📊 Scoring Breakdown</h3>
                <table style="width:100%;border-collapse:collapse;font-size:14px;">
                    <tr style="background:#f9fafb;">
                        <th style="padding:8px 12px;text-align:left;">Dimension</th>
                        <th style="padding:8px 12px;text-align:center;">Score</th>
                        <th style="padding:8px 12px;"></th>
                        <th style="padding:8px 12px;text-align:left;">Reason</th>
                    </tr>
                    {score_rows}
                </table>

                <h3 style="margin:20px 0 8px;color:#111827;">⚠️ Risks</h3>
                <ul style="margin:0;padding-left:20px;color:#dc2626;">{risk_items}</ul>

                <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;">
                <p style="color:#9ca3af;font-size:12px;margin:0;">
                    OpportunityScout • ID: {opp.get('id', 'N/A')} • Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
                </p>
            </div>
        </div>"""

    def _render_daily_digest(self, opportunities: list, signals: list,
                              trends: list, date_str: str) -> str:
        """Render daily digest as HTML."""
        opp_rows = ""
        if opportunities:
            for i, opp in enumerate(opportunities[:10], 1):
                tier = opp.get('tier', '')
                emoji = {'FIRE': '🔥', 'HIGH': '⭐', 'MEDIUM': '📊'}.get(tier, '📝')
                color = {'FIRE': '#dc2626', 'HIGH': '#f59e0b', 'MEDIUM': '#3b82f6'}.get(tier, '#6b7280')
                score = opp.get('weighted_total', 0)

                opp_rows += f"""
                <tr style="border-bottom:1px solid #f3f4f6;">
                    <td style="padding:12px;font-size:16px;">{emoji}</td>
                    <td style="padding:12px;">
                        <div style="font-weight:600;color:#111827;">{opp.get('title', '?')}</div>
                        <div style="color:#6b7280;font-size:13px;margin-top:4px;">{opp.get('one_liner', '')}</div>
                        <div style="color:#9ca3af;font-size:12px;margin-top:4px;">
                            Sector: {opp.get('sector', 'N/A')} • {opp.get('geography', '')}
                        </div>
                    </td>
                    <td style="padding:12px;text-align:center;">
                        <span style="background:{color};color:white;padding:4px 10px;border-radius:12px;font-weight:bold;font-size:14px;">
                            {score}
                        </span>
                    </td>
                    <td style="padding:12px;font-size:13px;color:#374151;">
                        {opp.get('first_move', 'N/A')}
                    </td>
                </tr>"""

        signal_items = ""
        if signals:
            for s in signals[:5]:
                signal_items += f'<li style="margin:6px 0;">{s.get("summary", str(s))}</li>'

        trend_items = ""
        if trends:
            for t in trends[:5]:
                trend_items += f'<span style="background:#e0e7ff;color:#4338ca;padding:4px 12px;border-radius:12px;margin:4px;display:inline-block;font-size:13px;">{t}</span>'

        return f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:700px;margin:0 auto;background:#ffffff;">
            <div style="background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:24px;border-radius:8px 8px 0 0;">
                <h1 style="color:white;margin:0;font-size:20px;">📊 Daily Intelligence Brief</h1>
                <p style="color:#93c5fd;margin:8px 0 0;font-size:14px;">{date_str}</p>
            </div>
            <div style="padding:24px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;">
                <h2 style="margin:0 0 12px;color:#111827;font-size:16px;">🏆 Top Opportunities</h2>
                <table style="width:100%;border-collapse:collapse;">
                    <tr style="background:#f9fafb;font-size:13px;color:#6b7280;">
                        <th style="padding:8px;"></th>
                        <th style="padding:8px;text-align:left;">Opportunity</th>
                        <th style="padding:8px;text-align:center;">Score</th>
                        <th style="padding:8px;text-align:left;">First Move</th>
                    </tr>
                    {opp_rows}
                </table>

                {"<h2 style='margin:20px 0 12px;font-size:16px;'>📡 Key Signals</h2><ul>" + signal_items + "</ul>" if signal_items else ""}
                {"<h2 style='margin:20px 0 12px;font-size:16px;'>📈 Trend Watch</h2><div>" + trend_items + "</div>" if trend_items else ""}

                <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;">
                <p style="color:#9ca3af;font-size:12px;margin:0;">
                    OpportunityScout Daily Brief • {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
                </p>
            </div>
        </div>"""

    def _render_weekly_report(self, report_data: dict, date_str: str) -> str:
        """Render weekly strategic report as HTML."""
        stats = report_data.get('stats', {})
        summary = report_data.get('summary', 'No summary available.')
        opps = report_data.get('top_opportunities', [])
        actions = report_data.get('recommended_actions', [])

        opp_cards = ""
        for i, opp in enumerate(opps[:10], 1):
            tier = opp.get('tier', '')
            emoji = {'FIRE': '🔥', 'HIGH': '⭐', 'MEDIUM': '📊'}.get(tier, '📝')
            score = opp.get('weighted_total', 0)
            opp_cards += f"""
            <div style="background:#f9fafb;padding:12px 16px;border-radius:6px;margin-bottom:8px;border-left:3px solid {'#dc2626' if tier == 'FIRE' else '#f59e0b' if tier == 'HIGH' else '#3b82f6'};">
                <div style="font-weight:600;">{emoji} {opp.get('title', '?')}</div>
                <div style="color:#6b7280;font-size:13px;margin-top:4px;">
                    Score: {score}/155 • {opp.get('sector', 'N/A')} • {opp.get('geography', '')}
                </div>
                <div style="color:#374151;font-size:13px;margin-top:4px;">{opp.get('one_liner', '')}</div>
            </div>"""

        action_items = ""
        for i, action in enumerate(actions[:5], 1):
            action_items += f'<li style="margin:8px 0;">{action}</li>'

        return f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:700px;margin:0 auto;background:#ffffff;">
            <div style="background:linear-gradient(135deg,#1e3a5f,#7c3aed);padding:24px;border-radius:8px 8px 0 0;">
                <h1 style="color:white;margin:0;font-size:20px;">📋 Weekly Strategy Report</h1>
                <p style="color:#c4b5fd;margin:8px 0 0;font-size:14px;">Week of {date_str}</p>
            </div>
            <div style="padding:24px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;">

                <h2 style="margin:0 0 8px;font-size:16px;">Executive Summary</h2>
                <p style="color:#374151;line-height:1.6;">{summary}</p>

                <div style="display:flex;gap:12px;margin:20px 0;">
                    <div style="flex:1;background:#f0fdf4;padding:16px;border-radius:8px;text-align:center;">
                        <div style="font-size:24px;font-weight:bold;color:#16a34a;">{stats.get('new_opportunities', 0)}</div>
                        <div style="color:#6b7280;font-size:12px;">New Opportunities</div>
                    </div>
                    <div style="flex:1;background:#fef2f2;padding:16px;border-radius:8px;text-align:center;">
                        <div style="font-size:24px;font-weight:bold;color:#dc2626;">{stats.get('fire_count', 0)}</div>
                        <div style="color:#6b7280;font-size:12px;">Fire Alerts</div>
                    </div>
                    <div style="flex:1;background:#eff6ff;padding:16px;border-radius:8px;text-align:center;">
                        <div style="font-size:24px;font-weight:bold;color:#2563eb;">{stats.get('sources_scanned', 0)}</div>
                        <div style="color:#6b7280;font-size:12px;">Sources Scanned</div>
                    </div>
                    <div style="flex:1;background:#faf5ff;padding:16px;border-radius:8px;text-align:center;">
                        <div style="font-size:24px;font-weight:bold;color:#7c3aed;">{stats.get('avg_score', 0)}</div>
                        <div style="color:#6b7280;font-size:12px;">Avg Score</div>
                    </div>
                </div>

                <h2 style="margin:20px 0 12px;font-size:16px;">🏆 Top Opportunities</h2>
                {opp_cards}

                {"<h2 style='margin:20px 0 12px;font-size:16px;'>🎯 Recommended Actions</h2><ol style='padding-left:20px;'>" + action_items + "</ol>" if action_items else ""}

                <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;">
                <p style="color:#9ca3af;font-size:12px;margin:0;">
                    OpportunityScout Weekly Report • {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
                </p>
            </div>
        </div>"""

    def _render_scan_report(self, scan_results: dict, all_opportunities: list,
                               date_str: str, tier_label: str) -> str:
        """Render comprehensive scan completion report as HTML."""
        stats = scan_results.get('combined_stats', scan_results)
        duration = scan_results.get('total_duration', 0)
        brain_synced = scan_results.get('brain_synced', 0)

        # Tier breakdown
        tier_stats = scan_results.get('tier_stats', {})
        tier_rows = ""
        for t_key, t_data in sorted(tier_stats.items()):
            tier_rows += f"""
            <tr style="border-bottom:1px solid #f3f4f6;">
                <td style="padding:10px 16px;font-weight:600;">{t_key}</td>
                <td style="padding:10px 16px;text-align:center;">{t_data.get('sources_scanned', 0)}</td>
                <td style="padding:10px 16px;text-align:center;">{t_data.get('items_collected', 0)}</td>
                <td style="padding:10px 16px;text-align:center;font-weight:bold;">{t_data.get('opportunities_found', 0)}</td>
                <td style="padding:10px 16px;text-align:center;">{t_data.get('fire_alerts', 0)}</td>
                <td style="padding:10px 16px;text-align:center;">{t_data.get('high_alerts', 0)}</td>
            </tr>"""

        # Sort opportunities by score
        sorted_opps = sorted(
            all_opportunities,
            key=lambda x: x.get('weighted_total', 0),
            reverse=True
        )[:20]

        # Opportunity cards
        opp_cards = ""
        for i, opp in enumerate(sorted_opps, 1):
            tier = opp.get('tier', '')
            emoji = {'FIRE': '🔥', 'HIGH': '⭐', 'MEDIUM': '📊'}.get(tier, '📝')
            score = opp.get('weighted_total', 0)
            border_color = {'FIRE': '#dc2626', 'HIGH': '#f59e0b', 'MEDIUM': '#3b82f6'}.get(tier, '#9ca3af')
            badge_bg = {'FIRE': '#fef2f2', 'HIGH': '#fffbeb', 'MEDIUM': '#eff6ff'}.get(tier, '#f9fafb')
            badge_color = {'FIRE': '#dc2626', 'HIGH': '#d97706', 'MEDIUM': '#2563eb'}.get(tier, '#6b7280')

            risks = opp.get('risks', [])
            if isinstance(risks, str):
                import json as _json
                try:
                    risks = _json.loads(risks)
                except Exception:
                    risks = [risks]
            risk_str = ', '.join(risks[:2]) if risks else 'N/A'

            opp_cards += f"""
            <div style="background:#ffffff;border:1px solid #e5e7eb;border-left:4px solid {border_color};border-radius:6px;padding:16px;margin-bottom:12px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
                    <div style="font-weight:700;font-size:15px;color:#111827;">
                        {emoji} #{i} — {opp.get('title', '?')}
                    </div>
                    <div style="background:{badge_bg};color:{badge_color};padding:4px 12px;border-radius:12px;font-weight:700;font-size:13px;white-space:nowrap;margin-left:12px;">
                        {score}/155
                    </div>
                </div>
                <div style="color:#4b5563;font-size:14px;font-style:italic;margin-bottom:10px;">
                    {opp.get('one_liner', '')}
                </div>
                <table style="width:100%;font-size:13px;color:#374151;">
                    <tr>
                        <td style="padding:3px 0;"><strong>Sector:</strong> {opp.get('sector', 'N/A')}</td>
                        <td style="padding:3px 0;"><strong>Geography:</strong> {opp.get('geography', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding:3px 0;" colspan="2"><strong>Why NOW:</strong> {opp.get('why_now', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding:3px 0;" colspan="2"><strong>First Move:</strong> {opp.get('first_move', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding:3px 0;" colspan="2"><strong>Revenue:</strong> {opp.get('revenue_path', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding:3px 0;" colspan="2"><strong>Risks:</strong> <span style="color:#dc2626;">{risk_str}</span></td>
                    </tr>
                </table>
                <div style="margin-top:8px;font-size:11px;color:#9ca3af;">
                    ID: {opp.get('id', 'N/A')} • Source: {opp.get('source', 'N/A')}
                </div>
            </div>"""

        # Sector distribution
        sector_counts = {}
        for opp in all_opportunities:
            s = opp.get('sector', 'Unknown')
            sector_counts[s] = sector_counts.get(s, 0) + 1
        sector_sorted = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)

        sector_bars = ""
        max_count = max(sector_counts.values()) if sector_counts else 1
        for sector, count in sector_sorted[:10]:
            bar_width = int((count / max_count) * 200)
            sector_bars += f"""
            <div style="display:flex;align-items:center;margin:4px 0;">
                <div style="width:140px;font-size:13px;color:#374151;flex-shrink:0;">{sector}</div>
                <div style="background:#3b82f6;height:16px;width:{bar_width}px;border-radius:3px;margin-right:8px;"></div>
                <div style="font-size:13px;font-weight:600;color:#111827;">{count}</div>
            </div>"""

        # Tier distribution
        tier_dist = {'FIRE': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        for opp in all_opportunities:
            t = opp.get('tier', 'LOW')
            tier_dist[t] = tier_dist.get(t, 0) + 1

        total_sources = stats.get('sources_scanned', sum(
            t.get('sources_scanned', 0) for t in tier_stats.values()
        ))
        total_opps = len(all_opportunities)
        total_fire = tier_dist.get('FIRE', 0)
        total_high = tier_dist.get('HIGH', 0)

        minutes = int(duration // 60)
        seconds = int(duration % 60)
        duration_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

        return f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:750px;margin:0 auto;background:#ffffff;">
            <div style="background:linear-gradient(135deg,#0f172a,#1e40af);padding:28px;border-radius:8px 8px 0 0;">
                <h1 style="color:white;margin:0;font-size:22px;">📡 Scan Completion Report</h1>
                <p style="color:#93c5fd;margin:8px 0 0;font-size:14px;">
                    Tier {tier_label} • {date_str}
                </p>
            </div>
            <div style="padding:24px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;">

                <!-- Stats Cards -->
                <div style="display:flex;gap:10px;margin-bottom:24px;">
                    <div style="flex:1;background:#f0fdf4;padding:14px;border-radius:8px;text-align:center;">
                        <div style="font-size:28px;font-weight:bold;color:#16a34a;">{total_opps}</div>
                        <div style="color:#6b7280;font-size:11px;">Opportunities</div>
                    </div>
                    <div style="flex:1;background:#fef2f2;padding:14px;border-radius:8px;text-align:center;">
                        <div style="font-size:28px;font-weight:bold;color:#dc2626;">{total_fire}</div>
                        <div style="color:#6b7280;font-size:11px;">FIRE</div>
                    </div>
                    <div style="flex:1;background:#fffbeb;padding:14px;border-radius:8px;text-align:center;">
                        <div style="font-size:28px;font-weight:bold;color:#d97706;">{total_high}</div>
                        <div style="color:#6b7280;font-size:11px;">HIGH</div>
                    </div>
                    <div style="flex:1;background:#eff6ff;padding:14px;border-radius:8px;text-align:center;">
                        <div style="font-size:28px;font-weight:bold;color:#2563eb;">{total_sources}</div>
                        <div style="color:#6b7280;font-size:11px;">Sources</div>
                    </div>
                    <div style="flex:1;background:#faf5ff;padding:14px;border-radius:8px;text-align:center;">
                        <div style="font-size:28px;font-weight:bold;color:#7c3aed;">{brain_synced}</div>
                        <div style="color:#6b7280;font-size:11px;">Brain Sync</div>
                    </div>
                    <div style="flex:1;background:#f9fafb;padding:14px;border-radius:8px;text-align:center;">
                        <div style="font-size:28px;font-weight:bold;color:#374151;">{duration_str}</div>
                        <div style="color:#6b7280;font-size:11px;">Duration</div>
                    </div>
                </div>

                <!-- Tier Breakdown -->
                {"<h2 style='margin:0 0 12px;font-size:16px;color:#111827;'>📊 Tier Breakdown</h2><table style=width:100%;border-collapse:collapse;font-size:14px;margin-bottom:24px;><tr style=background:#f9fafb;><th style=padding:8px 16px;text-align:left;>Tier</th><th style=padding:8px 16px;text-align:center;>Sources</th><th style=padding:8px 16px;text-align:center;>Items</th><th style=padding:8px 16px;text-align:center;>Opportunities</th><th style=padding:8px 16px;text-align:center;>FIRE</th><th style=padding:8px 16px;text-align:center;>HIGH</th></tr>" + tier_rows + "</table>" if tier_rows else ""}

                <!-- Sector Distribution -->
                <h2 style="margin:0 0 12px;font-size:16px;color:#111827;">🏷️ Sector Distribution</h2>
                <div style="background:#f9fafb;padding:16px;border-radius:8px;margin-bottom:24px;">
                    {sector_bars if sector_bars else '<p style="color:#6b7280;">No sector data available.</p>'}
                </div>

                <!-- Tier Distribution -->
                <div style="background:#f9fafb;padding:16px;border-radius:8px;margin-bottom:24px;display:flex;gap:16px;justify-content:center;">
                    <div style="text-align:center;">
                        <span style="font-size:20px;">🔥</span>
                        <div style="font-weight:bold;">{tier_dist.get('FIRE', 0)}</div>
                        <div style="font-size:11px;color:#6b7280;">FIRE</div>
                    </div>
                    <div style="text-align:center;">
                        <span style="font-size:20px;">⭐</span>
                        <div style="font-weight:bold;">{tier_dist.get('HIGH', 0)}</div>
                        <div style="font-size:11px;color:#6b7280;">HIGH</div>
                    </div>
                    <div style="text-align:center;">
                        <span style="font-size:20px;">📊</span>
                        <div style="font-weight:bold;">{tier_dist.get('MEDIUM', 0)}</div>
                        <div style="font-size:11px;color:#6b7280;">MEDIUM</div>
                    </div>
                    <div style="text-align:center;">
                        <span style="font-size:20px;">📝</span>
                        <div style="font-weight:bold;">{tier_dist.get('LOW', 0)}</div>
                        <div style="font-size:11px;color:#6b7280;">LOW</div>
                    </div>
                </div>

                <!-- Top 15 Opportunities -->
                <h2 style="margin:0 0 16px;font-size:16px;color:#111827;">🏆 Top 20 Opportunities</h2>
                {opp_cards if opp_cards else '<p style="color:#6b7280;">No opportunities found this scan.</p>'}

                <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0 16px;">
                <p style="color:#9ca3af;font-size:12px;margin:0;text-align:center;">
                    OpportunityScout Scan Report • Tier {tier_label} • {date_str}<br>
                    Powered by Claude API + Open Brain
                </p>
            </div>
        </div>"""

    # ─── SES API Sender ─────────────────────────────────────

    def _send(self, subject: str, html_body: str):
        """Send HTML email via AWS SES API."""
        if not self.enabled:
            logger.info(f"[EMAIL SKIP] {subject}")
            return

        import re
        plain = html_body.replace('<br>', '\n').replace('</div>', '\n')
        plain = re.sub('<[^<]+?>', '', plain)

        try:
            self.ses_client.send_email(
                Source=self.from_email,
                Destination={'ToAddresses': [self.to_email]},
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': {
                        'Text': {'Data': plain, 'Charset': 'UTF-8'},
                        'Html': {'Data': html_body, 'Charset': 'UTF-8'}
                    }
                }
            )
            logger.info(f"Email sent: {subject}")
        except Exception as e:
            logger.error(f"Email send failed: {e}")
