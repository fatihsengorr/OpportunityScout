"""
OpportunityScout — Temporal Intelligence Module

Tracks regulatory deadlines, market cycles, and timing windows.
Publishes deadline_approaching events at 180, 90, 30, 7 day marks.
Other modules subscribe and auto-focus searches on approaching deadlines.

Features:
- Loads regulatory_calendar.yaml with known deadlines
- Monthly web search to discover NEW deadlines
- Publishes events at threshold intervals
- Provides temporal scoring boost info to scoring pipeline
"""

import json
import logging
import yaml
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("scout.temporal")


class TemporalIntelligence:
    """
    Tracks time-sensitive opportunities: regulatory deadlines,
    market cycles, seasonal patterns.
    """

    ALERT_THRESHOLDS = [180, 90, 30, 7]  # days before deadline to alert

    def __init__(self, config: dict, knowledge_base, event_bus=None):
        self.config = config
        self.kb = knowledge_base
        self.event_bus = event_bus
        self.calendar_path = Path("./config/regulatory_calendar.yaml")
        self._load_and_sync_calendar()

    def _load_and_sync_calendar(self):
        """Load regulatory calendar and sync to KB."""
        try:
            with open(self.calendar_path) as f:
                data = yaml.safe_load(f) or {}

            deadlines = data.get('deadlines', [])
            for dl in deadlines:
                self.kb.save_deadline(
                    name=dl['name'],
                    deadline_date=dl['deadline_date'],
                    jurisdiction=', '.join(dl.get('regions', [])),
                    capabilities=dl.get('capabilities', []),
                    impact=dl.get('impact', ''),
                    search_queries=dl.get('search_queries', [])
                )

            logger.info(f"📅 Loaded {len(deadlines)} regulatory deadlines")
        except FileNotFoundError:
            logger.warning("regulatory_calendar.yaml not found")
        except Exception as e:
            logger.error(f"Failed to load regulatory calendar: {e}")

    def check_deadlines(self) -> list:
        """
        Check all deadlines and publish events for approaching ones.
        Returns list of approaching deadline alerts.
        """
        alerts = []
        now = datetime.utcnow().date()

        try:
            # Get all deadlines from KB
            deadlines = self.kb.get_approaching_deadlines(days=365)
        except Exception as e:
            logger.error(f"Failed to get deadlines: {e}")
            return alerts

        for dl in deadlines:
            try:
                deadline_date = datetime.strptime(
                    dl['deadline_date'], '%Y-%m-%d'
                ).date()
            except (ValueError, KeyError):
                continue

            days_remaining = (deadline_date - now).days

            if days_remaining < 0:
                continue  # Past deadline

            # Check each threshold
            for threshold in self.ALERT_THRESHOLDS:
                if days_remaining <= threshold:
                    alert = {
                        'name': dl['name'],
                        'deadline_date': dl['deadline_date'],
                        'days_remaining': days_remaining,
                        'threshold': threshold,
                        'description': dl.get('description', ''),
                        'capabilities': self._parse_json(dl.get('capabilities', '[]')),
                        'impact': dl.get('impact', ''),
                        'search_queries': self._parse_json(dl.get('search_queries', '[]')),
                        'urgency': self._urgency_level(days_remaining)
                    }
                    alerts.append(alert)

                    # Publish event
                    if self.event_bus:
                        self.event_bus.publish('deadline_approaching', {
                            'name': dl['name'],
                            'days_remaining': days_remaining,
                            'urgency': alert['urgency'],
                            'capabilities': alert['capabilities'],
                            'search_queries': alert['search_queries']
                        }, source_module='temporal_intelligence')

                    break  # Only alert at the most relevant threshold

        if alerts:
            logger.info(f"📅 {len(alerts)} approaching deadlines detected")

        return alerts

    def get_temporal_boost(self, opportunity: dict) -> float:
        """
        Calculate temporal scoring boost for an opportunity.
        Opportunities aligned with 90-day deadlines get +1 to market_timing.
        Returns boost value (0.0 or 1.0).
        """
        opp_tags = set(t.lower() for t in opportunity.get('tags', []))
        opp_sector = opportunity.get('sector', '').lower()

        try:
            deadlines = self.kb.get_approaching_deadlines(days=90)
        except Exception:
            return 0.0

        for dl in deadlines:
            capabilities = self._parse_json(dl.get('capabilities', '[]'))
            # Check if opportunity aligns with any deadline capability
            for cap in capabilities:
                cap_lower = cap.lower().replace('_', '-')
                if cap_lower in opp_tags or cap_lower in opp_sector:
                    return 1.0  # Temporal boost!
                # Also check partial matches
                for tag in opp_tags:
                    if cap_lower in tag or tag in cap_lower:
                        return 1.0

        return 0.0

    def get_deadline_report(self) -> str:
        """Generate a formatted deadline report for Telegram/CLI."""
        now = datetime.utcnow().date()

        try:
            deadlines = self.kb.get_approaching_deadlines(days=365)
        except Exception:
            return "No deadline data available."

        if not deadlines:
            return "No approaching deadlines found."

        lines = ["📅 REGULATORY DEADLINE TRACKER\n"]
        lines.append("=" * 40)

        for dl in deadlines:
            try:
                deadline_date = datetime.strptime(
                    dl['deadline_date'], '%Y-%m-%d'
                ).date()
                days_remaining = (deadline_date - now).days
            except (ValueError, KeyError):
                continue

            if days_remaining < 0:
                continue

            urgency = self._urgency_level(days_remaining)
            emoji = {'CRITICAL': '🔴', 'HIGH': '🟠', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(
                urgency, '⚪'
            )

            capabilities = self._parse_json(dl.get('capabilities', '[]'))
            cap_str = ', '.join(capabilities) if capabilities else 'general'

            lines.append(
                f"\n{emoji} {dl['name']}\n"
                f"   Date: {dl['deadline_date']} ({days_remaining} days)\n"
                f"   Urgency: {urgency}\n"
                f"   Capabilities: {cap_str}\n"
                f"   Impact: {dl.get('impact', 'N/A')[:100]}"
            )

        return '\n'.join(lines)

    def _urgency_level(self, days: int) -> str:
        """Map days remaining to urgency level."""
        if days <= 7:
            return 'CRITICAL'
        elif days <= 30:
            return 'HIGH'
        elif days <= 90:
            return 'MEDIUM'
        else:
            return 'LOW'

    @staticmethod
    def _parse_json(value):
        """Safely parse JSON string or return as-is if already parsed."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        return value if isinstance(value, list) else []
