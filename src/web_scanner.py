"""
OpportunityScout — Web Scanner (Adaptive Source Engine v2)

Fetches content from configured sources: RSS feeds, web searches,
Reddit, APIs, and custom scrapers. Normalizes everything into a
common format for the analysis engine.

v2 Upgrades:
- Dynamic query templates with variable resolution
- Source performance tracking (auto-promote/demote via self-improver)
- Novelty filter to deprioritize repetitive content
- Source discovery (ask Claude for new feeds/subreddits)
"""

import asyncio
import aiohttp
import feedparser
import json
import logging
import time
import re
import yaml
import random
from datetime import datetime
from typing import Optional
from pathlib import Path
from urllib.parse import quote_plus

logger = logging.getLogger("scout.scanner")


class ContentItem:
    """Normalized content item from any source."""

    def __init__(self, title: str, content: str, url: str,
                 source_name: str, published: str = None,
                 tags: list = None):
        self.title = title
        self.content = content[:3000]  # Truncate for API limits
        self.url = url
        self.source_name = source_name
        self.published = published or datetime.utcnow().isoformat()
        self.tags = tags or []

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "source_name": self.source_name,
            "published": self.published,
            "tags": self.tags
        }

    def __repr__(self):
        return f"<ContentItem: {self.title[:60]}>"


class WebScanner:
    """Multi-source content fetcher with rate limiting and dynamic queries."""

    def __init__(self, config: dict):
        self.config = config
        self.rate_limit = config.get('rate_limits', {})
        self.delay = self.rate_limit.get('delay_between_sources_seconds', 3)
        self.max_per_minute = self.rate_limit.get('max_web_requests_per_minute', 10)
        self._request_times = []
        self._recent_titles = []  # For novelty filtering
        self._sector_rotation = self._load_sector_rotation()

    def _load_sector_rotation(self) -> dict:
        """Load current sector rotation config."""
        try:
            with open('./config/sector_rotation.yaml') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}

    def _get_current_rotation(self) -> dict:
        """Get this week's rotation focus based on day of month."""
        rotation = self._sector_rotation.get('rotation', {})
        if not rotation:
            return {}
        day = datetime.utcnow().day
        week_num = min((day - 1) // 7 + 1, 5)  # 1-5
        week_key = f"week_{week_num}"
        return rotation.get(week_key, rotation.get('week_1', {}))

    # ─── Dynamic Query Resolution ────────────────────────────

    def resolve_query_template(self, source: dict) -> str:
        """
        Resolve dynamic query templates with current context variables.

        Template variables:
        - {trending_sector} → Current rotation focus sector
        - {approaching_deadline} → Nearest regulatory deadline
        - {blind_spot} → Random underexplored area
        - {random_adjacent} → Random adjacent industry from capability map
        - {year} → Current year
        - {quarter} → Current quarter (Q1-Q4)
        """
        # Use query_template if available, fall back to query
        template = source.get('query_template', source.get('query', ''))

        if not template or '{' not in template:
            # No template variables, return as-is
            return template

        # Build variable context
        rotation = self._get_current_rotation()
        now = datetime.utcnow()
        quarter = f"Q{(now.month - 1) // 3 + 1}"

        variables = {
            'year': str(now.year),
            'quarter': quarter,
            'trending_sector': self._pick_trending_sector(rotation),
            'approaching_deadline': self._pick_deadline(),
            'blind_spot': self._pick_blind_spot(),
            'random_adjacent': self._pick_random_adjacent(),
            'rotation_keyword': self._pick_rotation_keyword(rotation),
        }

        # Resolve template
        resolved = template
        for var, value in variables.items():
            resolved = resolved.replace(f'{{{var}}}', value)

        return resolved

    def _pick_trending_sector(self, rotation: dict) -> str:
        """Pick a trending sector from current rotation."""
        sectors = rotation.get('sectors', [])
        if sectors:
            return random.choice(sectors)
        # Fallback pool (non-construction focused)
        fallback = [
            'cybersecurity', 'AI automation', 'cross-border e-commerce',
            'managed IT services', 'proptech SaaS', 'compliance tech',
            'industrial IoT', 'supply chain tech'
        ]
        return random.choice(fallback)

    def _pick_deadline(self) -> str:
        """Pick an approaching regulatory deadline."""
        # Will be enhanced when temporal_intelligence is built
        deadlines = [
            'NIS2 cybersecurity directive 2026',
            'BSA building safety golden thread 2026',
            'MEES EPC-C regulations 2027',
            'UK Cyber Essentials expansion',
            'EU AI Act compliance requirements',
        ]
        return random.choice(deadlines)

    def _pick_blind_spot(self) -> str:
        """Pick an underexplored area."""
        blind_spots = [
            'managed SOC services UK SMEs',
            'VDI remote work solutions',
            'AI workflow automation',
            'cross-border trade platforms',
            'healthcare IT managed services',
            'legal tech document AI',
            'education platform B2B',
            'industrial coatings innovation',
        ]
        return random.choice(blind_spots)

    def _pick_random_adjacent(self) -> str:
        """Pick a random adjacent industry from capability map."""
        try:
            with open('./config/capability_map.yaml') as f:
                data = yaml.safe_load(f)
            all_industries = []
            for cluster in data.get('capabilities', {}).values():
                for ind in cluster.get('adjacent_industries', []):
                    if isinstance(ind, dict):
                        all_industries.append(ind.get('name', '').replace('_', ' '))
                    else:
                        all_industries.append(str(ind).replace('_', ' '))
            if all_industries:
                return random.choice(all_industries)
        except Exception:
            pass
        return 'managed IT services'

    def _pick_rotation_keyword(self, rotation: dict) -> str:
        """Pick a keyword from current rotation."""
        keywords = rotation.get('keywords', [])
        if keywords:
            return random.choice(keywords)
        return 'business opportunities UK 2026'

    # ─── Novelty Filter ──────────────────────────────────────

    def _novelty_score(self, item: ContentItem) -> float:
        """
        Score how novel a content item is (0.0=repetitive, 1.0=completely new).
        Based on title similarity to recent items and sector frequency.
        """
        title_lower = item.title.lower()

        # Check exact/near-duplicate titles
        for recent_title in self._recent_titles[-50:]:
            # Simple word overlap ratio
            title_words = set(title_lower.split())
            recent_words = set(recent_title.lower().split())
            if title_words and recent_words:
                overlap = len(title_words & recent_words) / max(len(title_words), len(recent_words))
                if overlap > 0.7:
                    return 0.1  # Very similar to recent

        # Check if tags are over-represented in recent items
        tag_penalty = 0.0
        item_tags = set(t.lower() for t in item.tags)
        construction_tags = {'construction', 'building', 'bim', 'fire-doors', 'fitout'}
        if item_tags & construction_tags:
            tag_penalty = 0.2  # Slight penalty for construction (over-represented)

        return max(0.1, 1.0 - tag_penalty)

    def prioritize_by_novelty(self, items: list) -> list:
        """
        Sort items by novelty score — novel items first, repetitive last.
        Does NOT remove items, just reorders.
        """
        scored = [(item, self._novelty_score(item)) for item in items]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Update recent titles cache
        for item in items:
            self._recent_titles.append(item.title)
        # Keep only last 100
        self._recent_titles = self._recent_titles[-100:]

        return [item for item, _ in scored]

    # ─── Core Scanning ───────────────────────────────────────

    async def scan_sources(self, sources: list, tier: int = None) -> list:
        """
        Scan all sources (optionally filtered by tier).
        Returns list of ContentItem objects, prioritized by novelty.
        """
        all_items = []
        filtered = sources if tier is None else [
            s for s in sources if s.get('tier') == tier
        ]

        logger.info(f"Scanning {len(filtered)} sources (tier={tier})")

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "OpportunityScout/1.0"}
        ) as session:
            for source in filtered:
                try:
                    await self._rate_limit_wait()
                    items = await self._scan_source(session, source)
                    all_items.extend(items)
                    logger.info(
                        f"  [{source['name']}] → {len(items)} items"
                    )
                except Exception as e:
                    logger.error(f"  [{source['name']}] ERROR: {e}")

        # Apply novelty prioritization
        all_items = self.prioritize_by_novelty(all_items)

        # Apply domain cap (max N items per domain to prevent echo chamber)
        max_per_domain = self.config.get('scanning', {}).get('max_per_domain', 2)
        all_items = self._apply_domain_cap(all_items, max_per_domain)

        logger.info(f"Total items collected: {len(all_items)} (novelty-prioritized, domain-capped)")
        return all_items

    @staticmethod
    def _apply_domain_cap(items: list, max_per_domain: int = 2) -> list:
        """Limit items per domain to prevent echo chamber from single sources."""
        from urllib.parse import urlparse
        skip_domains = {'reddit.com', 'news.ycombinator.com', 'twitter.com', 'x.com'}
        domain_counts = {}
        capped = []
        skipped = 0
        for item in items:
            url = getattr(item, 'url', '') or ''
            if not url:
                capped.append(item)
                continue
            try:
                domain = urlparse(url).netloc.lower().replace('www.', '')
            except Exception:
                capped.append(item)
                continue
            if domain in skip_domains or not domain:
                capped.append(item)
                continue
            if domain_counts.get(domain, 0) >= max_per_domain:
                skipped += 1
                continue
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            capped.append(item)
        if skipped:
            logger.info(f"  Domain cap: {skipped} items skipped (max {max_per_domain}/domain)")
        return capped

    async def _scan_source(self, session: aiohttp.ClientSession,
                           source: dict) -> list:
        """Route to appropriate scanner based on source type."""
        source_type = source.get('type', 'web_search')

        scanners = {
            'rss': self._scan_rss,
            'rss_or_scrape': self._scan_rss,
            'web_search': self._scan_web_search,
            'reddit': self._scan_reddit,
            'api': self._scan_api,
            'api_or_scrape': self._scan_web_search,
        }

        scanner = scanners.get(source_type, self._scan_web_search)
        return await scanner(session, source)

    async def _scan_rss(self, session: aiohttp.ClientSession,
                        source: dict) -> list:
        """Parse RSS/Atom feed."""
        items = []
        try:
            async with session.get(source['url']) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    feed = feedparser.parse(text)
                    for entry in feed.entries[:15]:
                        content = entry.get('summary', '') or entry.get('description', '')
                        content = self._strip_html(content)
                        items.append(ContentItem(
                            title=entry.get('title', 'Untitled'),
                            content=content,
                            url=entry.get('link', source['url']),
                            source_name=source['name'],
                            published=entry.get('published', ''),
                            tags=source.get('tags', [])
                        ))
        except Exception as e:
            logger.warning(f"RSS parse failed for {source['name']}: {e}")
        return items

    async def _scan_web_search(self, session: aiohttp.ClientSession,
                                source: dict) -> list:
        """
        Use web search to find relevant content.
        Now with dynamic query template resolution.
        """
        items = []

        # Resolve dynamic query template
        query = self.resolve_query_template(source)

        if not query:
            # Build query from URL and keywords
            keywords = source.get('query_params', {}).get('keywords', '')
            query = f"{source['name']} {keywords} latest news {datetime.utcnow().year}"

        # For web search, we return a search task for Claude API to execute
        items.append(ContentItem(
            title=f"[SEARCH_TASK] {query}",
            content=json.dumps({
                "action": "web_search",
                "query": query,
                "source_config": source
            }),
            url="",
            source_name=source['name'],
            tags=source.get('tags', [])
        ))
        return items

    async def _scan_reddit(self, session: aiohttp.ClientSession,
                           source: dict) -> list:
        """Fetch Reddit posts via JSON API."""
        items = []
        subreddit = source.get('subreddit', '')
        sort = source.get('sort', 'hot')
        limit = source.get('limit', 25)
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}"

        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for post in data.get('data', {}).get('children', []):
                        pd = post.get('data', {})
                        items.append(ContentItem(
                            title=pd.get('title', 'Untitled'),
                            content=(pd.get('selftext', '') or '')[:2000],
                            url=f"https://reddit.com{pd.get('permalink', '')}",
                            source_name=source['name'],
                            published=datetime.fromtimestamp(
                                pd.get('created_utc', 0)
                            ).isoformat() if pd.get('created_utc') else '',
                            tags=source.get('tags', []) + [
                                f"score:{pd.get('score', 0)}",
                                f"comments:{pd.get('num_comments', 0)}"
                            ]
                        ))
        except Exception as e:
            logger.warning(f"Reddit scan failed for r/{subreddit}: {e}")
        return items

    async def _scan_api(self, session: aiohttp.ClientSession,
                        source: dict) -> list:
        """Fetch from a generic JSON API (e.g., Hacker News)."""
        items = []
        try:
            async with session.get(source['url']) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    # Handle Hacker News specific format
                    if 'hacker-news' in source['url']:
                        story_ids = data[:20] if isinstance(data, list) else []
                        for sid in story_ids[:10]:
                            try:
                                async with session.get(
                                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json"
                                ) as item_resp:
                                    if item_resp.status == 200:
                                        story = await item_resp.json()
                                        if story and story.get('title'):
                                            items.append(ContentItem(
                                                title=story['title'],
                                                content=story.get('text', '') or f"URL: {story.get('url', '')}",
                                                url=story.get('url', f"https://news.ycombinator.com/item?id={sid}"),
                                                source_name=source['name'],
                                                published=datetime.fromtimestamp(
                                                    story.get('time', 0)
                                                ).isoformat() if story.get('time') else '',
                                                tags=source.get('tags', []) + [
                                                    f"points:{story.get('score', 0)}"
                                                ]
                                            ))
                                await asyncio.sleep(0.2)
                            except Exception:
                                continue
                    else:
                        items.append(ContentItem(
                            title=f"API Data: {source['name']}",
                            content=json.dumps(data)[:3000],
                            url=source['url'],
                            source_name=source['name'],
                            tags=source.get('tags', [])
                        ))
        except Exception as e:
            logger.warning(f"API scan failed for {source['name']}: {e}")
        return items

    # ─── Rate Limiting ──────────────────────────────────────

    async def _rate_limit_wait(self):
        """Enforce rate limiting between requests."""
        now = time.time()
        self._request_times = [
            t for t in self._request_times if now - t < 60
        ]
        if len(self._request_times) >= self.max_per_minute:
            wait_time = 60 - (now - self._request_times[0])
            if wait_time > 0:
                logger.debug(f"Rate limit: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
        if self._request_times:
            elapsed = now - self._request_times[-1]
            if elapsed < self.delay:
                await asyncio.sleep(self.delay - elapsed)
        self._request_times.append(time.time())

    # ─── Helpers ────────────────────────────────────────────

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags from text."""
        clean = re.sub(r'<[^>]+>', ' ', text)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()
