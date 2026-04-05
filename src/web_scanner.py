"""
OpportunityScout — Web Scanner

Fetches content from configured sources: RSS feeds, web searches,
Reddit, APIs, and custom scrapers. Normalizes everything into a
common format for the analysis engine.
"""

import asyncio
import aiohttp
import feedparser
import json
import logging
import time
import re
from datetime import datetime
from typing import Optional
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
    """Multi-source content fetcher with rate limiting."""

    def __init__(self, config: dict):
        self.config = config
        self.rate_limit = config.get('rate_limits', {})
        self.delay = self.rate_limit.get('delay_between_sources_seconds', 3)
        self.max_per_minute = self.rate_limit.get('max_web_requests_per_minute', 10)
        self._request_times = []

    async def scan_sources(self, sources: list, tier: int = None) -> list:
        """
        Scan all sources (optionally filtered by tier).
        Returns list of ContentItem objects.
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

        logger.info(f"Total items collected: {len(all_items)}")
        return all_items

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
            'api_or_scrape': self._scan_web_search,  # Fallback to search
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
                    for entry in feed.entries[:15]:  # Max 15 per source
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
        This creates search queries that Claude Code or n8n will execute 
        via the Anthropic API web_search tool or SerpAPI/Google Custom Search.
        """
        items = []
        query = source.get('query', source.get('url', ''))
        
        if not query:
            # Build query from URL and keywords
            keywords = source.get('query_params', {}).get('keywords', '')
            query = f"{source['name']} {keywords} latest news 2026"

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
                        for sid in story_ids[:10]:  # Top 10
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
                                await asyncio.sleep(0.2)  # Be nice to HN API
                            except Exception:
                                continue
                    else:
                        # Generic API: wrap entire response as a content item
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
        # Clean old timestamps
        self._request_times = [
            t for t in self._request_times if now - t < 60
        ]
        # If at limit, wait
        if len(self._request_times) >= self.max_per_minute:
            wait_time = 60 - (now - self._request_times[0])
            if wait_time > 0:
                logger.debug(f"Rate limit: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
        # Add delay between sources
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
