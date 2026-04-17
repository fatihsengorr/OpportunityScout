"""
Wildcatter Aile 1 — Bilim & Patent Scanner

Scans preprint servers (arXiv, bioRxiv, medRxiv), patent offices
(USPTO, EPO, TürkPatent), and academic alerts for early signals.

Philosophy (Open Brain, wildcatter/sources Aile 1):
"En az okunan ama en değerli sinyallerden. Yeni bir tekniğin yayınlanması
ile o tekniğin ürün olarak görülmesi arasında genelde 6-18 ay vardır.
Bu pencere arbitraj penceresidir."

Türk Patent Enstitüsü is specifically valuable:
"Türkiye'de patent koruması düşük olduğu için patent başvurusu = biri
gerçekten inşa etti sinyali."

Weekly Friday (same as Layer A tomography).
"""

import json
import logging
from datetime import datetime
from .llm_router import LLMRouter

logger = logging.getLogger("scout.family1")


class ScienceScanner:
    """Scan arXiv/bioRxiv/patent sources for early-signal items."""

    SEARCH_QUERIES = [
        # arXiv general
        {
            "name": "arXiv cs.AI",
            "query": "site:arxiv.org cs.AI new architecture breakthrough 2026 production viable",
            "category": "ai_research",
        },
        {
            "name": "arXiv cs.LG",
            "query": "site:arxiv.org cs.LG machine learning new technique commercial application 2026",
            "category": "ml_research",
        },
        {
            "name": "arXiv cond-mat.mtrl-sci",
            "query": "site:arxiv.org cond-mat materials science new material breakthrough coating intumescent 2026",
            "category": "materials",
        },
        # bioRxiv / medRxiv (DTC health focus)
        {
            "name": "bioRxiv longevity GLP-1",
            "query": "biorxiv.org OR medrxiv.org GLP-1 longevity senolytic new compound trial 2026",
            "category": "bio_dtc",
        },
        {
            "name": "medRxiv consumer health",
            "query": "medrxiv.org digital health wearable remote monitoring consumer trial 2026",
            "category": "consumer_health",
        },
        # Patents — Türk Patent specifically
        {
            "name": "TürkPatent new applications",
            "query": "site:turkpatent.gov.tr patent başvuru 2026 üretim teknoloji innovation",
            "category": "patent_tr",
            "special_note": "TR patent başvurusu = 'biri gerçekten inşa etti' sinyali",
        },
        {
            "name": "USPTO broader",
            "query": "site:patents.uspto.gov OR site:patents.google.com new patent 2025 2026 manufacturing IoT AI",
            "category": "patent_us",
        },
        {
            "name": "EPO Espacenet",
            "query": "site:worldwide.espacenet.com European patent 2026 materials construction AI",
            "category": "patent_eu",
        },
        # HuggingFace viral
        {
            "name": "HuggingFace Daily Papers",
            "query": "site:huggingface.co/papers viral trending AI technique 2026",
            "category": "ai_viral",
        },
    ]

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.llm = LLMRouter(config)
        self.model = self.llm.get_model('daily')  # Gemini with Google Search
        self._ensure_schema()

    def _ensure_schema(self):
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS science_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_category TEXT,
                title TEXT,
                authors TEXT,
                url TEXT,
                abstract TEXT,
                published_date TEXT,
                significance TEXT,
                detected_at TEXT DEFAULT (datetime('now')),
                processed INTEGER DEFAULT 0,
                UNIQUE(url)
            );
        """)
        self.kb.conn.commit()

    # ─── Public API ────────────────────────────────────────

    def scan_weekly(self, max_per_query: int = 3) -> dict:
        """Run all queries, persist new findings, return summary."""
        logger.info("🔬 Aile 1: Science & Patent scan starting")

        all_findings = []
        by_category = {}

        for query_spec in self.SEARCH_QUERIES:
            try:
                findings = self._run_query(query_spec, max_items=max_per_query)
                all_findings.extend(findings)
                by_category.setdefault(query_spec['category'], 0)
                by_category[query_spec['category']] += len(findings)
            except Exception as e:
                logger.warning(f"Science query '{query_spec['name']}' failed: {e}")

        logger.info(f"🔬 Aile 1 complete: {len(all_findings)} findings")
        return {
            'scan_date': datetime.utcnow().isoformat(),
            'total_findings': len(all_findings),
            'by_category': by_category,
            'findings': all_findings,
        }

    def _run_query(self, query_spec: dict, max_items: int) -> list:
        prompt = f"""Web'de ara: {query_spec['query']}

GÖREV: Son 30 gün içinde yayınlanan {max_items} SPESİFİK, TİCARİ DEĞERİ olan bulgu bul.

Her bulgu için:
- Başlık
- Yazar(lar) veya kurum
- Özet (2-3 cümle)
- Yayın tarihi
- Fatih için önemi (1 cümle): bu neden 6-18 ay içinde fırsat olabilir

SADECE son 30 güne odaklan, eski yayınları dahil ETME.
Abstract yetersizse bulguyu atla.

{'ÖZEL NOT: ' + query_spec['special_note'] if query_spec.get('special_note') else ''}

SADECE valid JSON:

{{
  "findings": [
    {{
      "title": "...",
      "authors": "...",
      "abstract": "2-3 cümle",
      "published_date": "YYYY-MM-DD",
      "url": "https://...",
      "significance": "Fatih için neden önemli"
    }}
  ]
}}"""

        try:
            response = self.llm.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
            )
            text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text += block.text
            parsed = self._parse_json(text)
        except Exception as e:
            logger.warning(f"Query fetch failed: {e}")
            return []

        findings = parsed.get('findings', []) if parsed else []

        # Persist unique ones
        stored = []
        cursor = self.kb.conn.cursor()
        for f in findings:
            url = f.get('url', '')
            if not url:
                continue
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO science_signals
                    (source_category, title, authors, url, abstract,
                     published_date, significance)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    query_spec['category'], f.get('title', '')[:300],
                    f.get('authors', '')[:200], url,
                    f.get('abstract', '')[:1000],
                    f.get('published_date', ''),
                    f.get('significance', '')[:500],
                ))
                self.kb.conn.commit()
                if cursor.rowcount > 0:
                    stored.append(f)
            except Exception as e:
                logger.warning(f"Science save failed: {e}")

        return stored

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        import re
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        start = text.find('{')
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i+1])
                        except json.JSONDecodeError:
                            break
        return {}

    def get_recent(self, days: int = 7) -> list:
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            SELECT * FROM science_signals
            WHERE detected_at >= datetime('now', '-' || ? || ' days')
            ORDER BY detected_at DESC
        """, (days,))
        return [dict(r) for r in cursor.fetchall()]
