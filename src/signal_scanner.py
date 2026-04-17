"""
OpportunityScout — External Signal Scanner

Two legally-safe early-signal sources:

1. **Google Jobs (via SerpAPI)** — Finds hiring signals in public Google Jobs results
   - "X company hiring 5 security engineers" = strategic direction reveal
   - 3-6 month lead time vs news coverage
   - TOS-safe (SerpAPI handles Google compliance)

2. **Crunchbase Funding (via public RSS / data feeds)**
   - Recent funding rounds in UK/TR/UAE
   - Filters to Series A-C (product-market-fit evidence)
   - Uses free public feeds — no Crunchbase Pro API required

Both sources feed intelligence_events for downstream engines to react to.

Requires:
  SERPAPI_KEY env var (optional — sign up at serpapi.com, 100 free/month)

Cost: ~$0.002/job-search via SerpAPI, Crunchbase RSS is free.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict

import httpx

logger = logging.getLogger("scout.signal_scanner")


class SignalScanner:
    """External signal sources beyond RSS/Reddit/HN."""

    SERPAPI_URL = "https://serpapi.com/search.json"

    # Keywords to search on Google Jobs — company+role patterns that reveal
    # strategic direction
    JOB_SIGNAL_QUERIES = [
        "site:linkedin.com/jobs UK cybersecurity engineer compliance",
        "site:linkedin.com/jobs UK AI automation senior engineer",
        "site:linkedin.com/jobs UK construction tech product manager",
        "site:linkedin.com/jobs UK building safety act compliance",
        "site:linkedin.com/jobs UK proptech startup founding engineer",
    ]

    # Crunchbase public feeds (free, no API key)
    # News feed at: https://news.crunchbase.com/feed/
    CRUNCHBASE_UK_NEWS = "https://news.crunchbase.com/category/fundings/feed/"

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.serpapi_key = os.environ.get("SERPAPI_KEY") or \
                           config.get('signals', {}).get('serpapi_key', '')
        self._ensure_schema()

    def _ensure_schema(self):
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS external_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,       -- 'google_jobs', 'crunchbase'
                signal_type TEXT,            -- 'hiring', 'funding', 'launch'
                company TEXT,
                title TEXT,
                url TEXT,
                summary TEXT,
                detected_at TEXT DEFAULT (datetime('now')),
                metadata_json TEXT,
                processed INTEGER DEFAULT 0,
                UNIQUE(source, url)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_external_signals_source ON external_signals(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_external_signals_processed ON external_signals(processed)")
        self.kb.conn.commit()

    # ─── Public API ────────────────────────────────────────

    async def scan_all(self) -> dict:
        """Run all signal sources, store new ones."""
        logger.info("📡 Running external signal scan...")
        total = {'google_jobs': 0, 'crunchbase': 0}

        # Google Jobs via SerpAPI (optional — only if key provided)
        if self.serpapi_key:
            try:
                hiring = await self.scan_hiring_signals()
                total['google_jobs'] = len(hiring)
            except Exception as e:
                logger.error(f"Hiring signal scan failed: {e}")
        else:
            logger.info("⚠️ SERPAPI_KEY not set — skipping hiring signals")

        # Crunchbase public feed (always free)
        try:
            funding = await self.scan_funding_signals()
            total['crunchbase'] = len(funding)
        except Exception as e:
            logger.error(f"Funding signal scan failed: {e}")

        logger.info(f"📡 Signal scan complete: {total}")
        return total

    # ─── Google Jobs (via SerpAPI) ─────────────────────────

    async def scan_hiring_signals(self) -> List[Dict]:
        """Fetch hiring signals via SerpAPI Google Jobs."""
        if not self.serpapi_key:
            return []

        new_signals = []
        async with httpx.AsyncClient(timeout=20) as client:
            for query in self.JOB_SIGNAL_QUERIES:
                try:
                    resp = await client.get(self.SERPAPI_URL, params={
                        "engine": "google_jobs",
                        "q": query.replace("site:linkedin.com/jobs ", ""),
                        "location": "United Kingdom",
                        "api_key": self.serpapi_key,
                        "num": 10,
                    })
                    if resp.status_code != 200:
                        logger.warning(f"SerpAPI returned {resp.status_code} for {query[:50]}")
                        continue
                    data = resp.json()
                    jobs = data.get('jobs_results', [])
                    for job in jobs[:10]:
                        signal = self._record_job(job, query)
                        if signal:
                            new_signals.append(signal)
                except Exception as e:
                    logger.warning(f"Query '{query[:40]}' failed: {e}")

        logger.info(f"📡 Hiring signals: {len(new_signals)} new")
        return new_signals

    def _record_job(self, job: dict, query: str):
        company = job.get('company_name', '')
        title = job.get('title', '')
        url = job.get('share_link') or job.get('apply_options', [{}])[0].get('link') or ''
        summary = (job.get('description', '') or '')[:500]

        if not company or not title:
            return None

        cursor = self.kb.conn.cursor()
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO external_signals
                (source, signal_type, company, title, url, summary, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                'google_jobs', 'hiring', company, title, url, summary,
                json.dumps({'query': query, 'location': job.get('location', '')})
            ))
            self.kb.conn.commit()
            if cursor.rowcount > 0:
                return {'company': company, 'title': title, 'url': url}
        except Exception as e:
            logger.warning(f"Failed to record job: {e}")
        return None

    # ─── Crunchbase News Feed ──────────────────────────────

    async def scan_funding_signals(self) -> List[Dict]:
        """Fetch UK funding rounds from Crunchbase News RSS."""
        try:
            import feedparser
        except ImportError:
            logger.warning("feedparser not installed — cannot scan Crunchbase")
            return []

        async with httpx.AsyncClient(timeout=20) as client:
            try:
                resp = await client.get(self.CRUNCHBASE_UK_NEWS)
                if resp.status_code != 200:
                    logger.warning(f"Crunchbase feed returned {resp.status_code}")
                    return []
                feed = feedparser.parse(resp.text)
            except Exception as e:
                logger.error(f"Crunchbase fetch failed: {e}")
                return []

        new_signals = []
        cutoff = datetime.utcnow() - timedelta(days=30)

        for entry in feed.entries[:50]:
            title = entry.get('title', '')
            url = entry.get('link', '')
            summary = (entry.get('summary', '') or '')[:500]

            # Filter to UK/Europe/relevant geographies
            haystack = (title + ' ' + summary).lower()
            if not any(k in haystack for k in
                       ['uk', 'united kingdom', 'london',
                        'turkey', 'turkish', 'istanbul',
                        'uae', 'dubai', 'emirates',
                        'europe']):
                continue

            # Extract company name (first capitalized token-sequence)
            # Crunchbase titles usually start with company name
            import re
            m = re.match(r'^([A-Z][\w&\-]+(?:\s+[A-Z][\w&\-]+){0,3})', title)
            company = m.group(1) if m else title[:40]

            cursor = self.kb.conn.cursor()
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO external_signals
                    (source, signal_type, company, title, url, summary)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, ('crunchbase', 'funding', company, title, url, summary))
                self.kb.conn.commit()
                if cursor.rowcount > 0:
                    new_signals.append({
                        'company': company, 'title': title, 'url': url
                    })
            except Exception as e:
                logger.warning(f"Failed to record funding: {e}")

        logger.info(f"📡 Funding signals: {len(new_signals)} new")
        return new_signals

    # ─── Query interface ──────────────────────────────────

    def get_recent_signals(self, source: str = None,
                           signal_type: str = None,
                           days: int = 7, limit: int = 50) -> List[Dict]:
        """Fetch recent signals — used by other engines."""
        cursor = self.kb.conn.cursor()
        where = ["detected_at >= datetime('now', '-' || ? || ' days')"]
        params = [days]
        if source:
            where.append("source = ?")
            params.append(source)
        if signal_type:
            where.append("signal_type = ?")
            params.append(signal_type)
        cursor.execute(f"""
            SELECT * FROM external_signals
            WHERE {' AND '.join(where)}
            ORDER BY detected_at DESC
            LIMIT ?
        """, params + [limit])
        return [dict(r) for r in cursor.fetchall()]

    def summary_for_telegram(self, days: int = 7) -> str:
        """Human-readable summary for /signals command."""
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            SELECT source, signal_type, COUNT(*) as cnt
            FROM external_signals
            WHERE detected_at >= datetime('now', '-' || ? || ' days')
            GROUP BY source, signal_type
        """, (days,))
        counts = cursor.fetchall()

        lines = [f"📡 *External Signals (last {days}d)*"]
        if not counts:
            lines.append("_No signals yet. Run `/signals scan` or enable SERPAPI_KEY._")
            return "\n".join(lines)

        for r in counts:
            lines.append(f"• {r['source']} / {r['signal_type']}: *{r['cnt']}*")

        # Top hiring companies
        cursor.execute("""
            SELECT company, COUNT(*) as cnt FROM external_signals
            WHERE source = 'google_jobs'
              AND detected_at >= datetime('now', '-' || ? || ' days')
            GROUP BY company
            ORDER BY cnt DESC LIMIT 5
        """, (days,))
        hiring_top = cursor.fetchall()
        if hiring_top:
            lines.append("\n*Top hiring companies:*")
            for r in hiring_top:
                lines.append(f"• {r['company']} ({r['cnt']} open roles)")

        # Recent funding
        cursor.execute("""
            SELECT company, title FROM external_signals
            WHERE source = 'crunchbase'
              AND detected_at >= datetime('now', '-' || ? || ' days')
            ORDER BY detected_at DESC LIMIT 5
        """, (days,))
        funding_recent = cursor.fetchall()
        if funding_recent:
            lines.append("\n*Recent funding:*")
            for r in funding_recent:
                lines.append(f"• {r['company']}: {r['title'][:80]}")

        return "\n".join(lines)
