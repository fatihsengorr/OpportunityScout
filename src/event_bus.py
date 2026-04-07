"""
OpportunityScout — Intelligence Event Bus

The nervous system of the Intelligence Mesh. Connects all modules via
publish-subscribe pattern with SQLite-backed persistence.

Events flow between modules:
- Web Scanner → signal_detected → Serendipity Engine (Strategy 1: Signal Chasing)
- Self-Improver → blind_spot_found → Capability Explorer
- Temporal Intelligence → deadline_approaching → Serendipity + Model Generator
- Any module → opportunity_scored → Cross-Pollinator
- Operator → operator_feedback → Self-Improver
- Capability Explorer → negative_evidence → Knowledge enrichment
- Cross-Pollinator → cross_pollination → Model Generator

Usage:
    bus = EventBus(kb)
    bus.subscribe("signal_detected", serendipity.on_signal)
    bus.subscribe("blind_spot_found", capability_explorer.on_blind_spot)
    bus.publish("signal_detected", {"type": "regulatory", "tags": ["nis2"], ...})
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


class EventBus:
    """In-process event bus with SQLite persistence for the Intelligence Mesh."""

    def __init__(self, kb=None):
        """
        Initialize the event bus.

        Args:
            kb: KnowledgeBase instance for event persistence.
                If None, events are in-memory only.
        """
        self.kb = kb
        self._subscribers: dict[str, list[Callable]] = {}
        self._event_queue: list[dict] = []
        self._processing = False

    def subscribe(self, event_type: str, handler: Callable):
        """
        Register a handler for an event type.

        Args:
            event_type: Event name (e.g., "signal_detected", "blind_spot_found")
            handler: Callable that accepts (event_data: dict) as argument.
                     Can be sync or async.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug(f"📡 Subscribed {handler.__qualname__} to '{event_type}'")

    def unsubscribe(self, event_type: str, handler: Callable):
        """Remove a handler from an event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]

    def publish(self, event_type: str, data: dict = None, source_module: str = None):
        """
        Publish an event to all subscribers.

        Args:
            event_type: Event name
            data: Event payload dict
            source_module: Name of the module that published this event
        """
        event = {
            'event_type': event_type,
            'data': data or {},
            'source_module': source_module or 'unknown',
            'timestamp': datetime.utcnow().isoformat(),
            'processed': False
        }

        # Persist to SQLite
        if self.kb:
            try:
                self.kb.save_event(event)
            except Exception as e:
                logger.warning(f"Failed to persist event: {e}")

        # Dispatch to subscribers
        handlers = self._subscribers.get(event_type, [])
        if not handlers:
            logger.debug(f"📡 Event '{event_type}' published (no subscribers)")
            return

        logger.info(
            f"📡 Event '{event_type}' from {event.get('source_module', '?')} "
            f"→ {len(handlers)} subscriber(s)"
        )

        for handler in handlers:
            try:
                result = handler(event['data'])
                # Handle async handlers
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        # No running loop — run synchronously
                        asyncio.run(result)
            except Exception as e:
                logger.error(
                    f"📡 Handler {handler.__qualname__} failed for "
                    f"'{event_type}': {e}"
                )

    async def publish_async(self, event_type: str, data: dict = None,
                            source_module: str = None):
        """Async version of publish — awaits async handlers."""
        event = {
            'event_type': event_type,
            'data': data or {},
            'source_module': source_module or 'unknown',
            'timestamp': datetime.utcnow().isoformat(),
            'processed': False
        }

        if self.kb:
            try:
                self.kb.save_event(event)
            except Exception as e:
                logger.warning(f"Failed to persist event: {e}")

        handlers = self._subscribers.get(event_type, [])
        if not handlers:
            return

        logger.info(
            f"📡 Event '{event_type}' from {event.get('source_module', '?')} "
            f"→ {len(handlers)} subscriber(s)"
        )

        for handler in handlers:
            try:
                result = handler(event['data'])
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(
                    f"📡 Handler {handler.__qualname__} failed for "
                    f"'{event_type}': {e}"
                )

    def get_unprocessed_events(self, event_type: str = None,
                                limit: int = 50) -> list:
        """
        Get unprocessed events from the persistent store.
        Used by Strategy 1 (Signal Chasing) to find events to react to.

        Args:
            event_type: Filter by event type. None = all types.
            limit: Max events to return.

        Returns:
            List of event dicts, oldest first.
        """
        if not self.kb:
            return []
        return self.kb.get_unprocessed_events(event_type, limit)

    def mark_processed(self, event_id: int):
        """Mark an event as processed."""
        if self.kb:
            self.kb.mark_event_processed(event_id)

    def get_recent_events(self, hours: int = 24,
                          event_type: str = None) -> list:
        """Get recent events for context building."""
        if not self.kb:
            return []
        return self.kb.get_recent_events(hours, event_type)

    def get_subscriber_count(self, event_type: str = None) -> dict:
        """Get subscriber counts for monitoring."""
        if event_type:
            return {event_type: len(self._subscribers.get(event_type, []))}
        return {et: len(handlers) for et, handlers in self._subscribers.items()}

    def get_event_stats(self) -> dict:
        """Get event statistics for the intelligence health dashboard."""
        if not self.kb:
            return {'total_events': 0, 'subscriber_count': self.get_subscriber_count()}
        return {
            'subscriber_count': self.get_subscriber_count(),
            **self.kb.get_event_stats()
        }
