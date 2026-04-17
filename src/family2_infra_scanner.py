"""
Wildcatter Aile 2 — Altyapı Hareketleri Scanner

Tracks infrastructure provider changelogs (Stripe, Anthropic, OpenAI,
Cloudflare, Vercel, Supabase, n8n, HuggingFace).

Philosophy (Open Brain, wildcatter/sources Aile 2):
"Bir şirket yeni bir B2B 'primitive' duyurduğunda, o primitive üzerine
yeni iş modelleri kurulabilir hale gelir. Bu pencere 6-12 ay açık kalır."

Weekly RSS aggregation — single scanner, all sources.
"""

import json
import logging
from datetime import datetime
from .llm_router import LLMRouter

logger = logging.getLogger("scout.family2")


class InfraLaunchScanner:
    """Scan infrastructure changelogs for new primitives / major launches."""

    SOURCES = [
        {
            "name": "Anthropic release notes",
            "url": "https://docs.anthropic.com/en/release-notes",
            "category": "ai_platform",
            "priority": 1,
        },
        {
            "name": "OpenAI changelog",
            "url": "https://platform.openai.com/docs/changelog",
            "category": "ai_platform",
            "priority": 1,
        },
        {
            "name": "Google AI announcements",
            "url": "https://ai.google.dev/release-notes",
            "category": "ai_platform",
            "priority": 1,
        },
        {
            "name": "Stripe blog",
            "url": "https://stripe.com/blog",
            "category": "fintech_infra",
            "priority": 2,
        },
        {
            "name": "Cloudflare blog",
            "url": "https://blog.cloudflare.com",
            "category": "edge_infra",
            "priority": 2,
        },
        {
            "name": "Vercel changelog",
            "url": "https://vercel.com/changelog",
            "category": "dev_platform",
            "priority": 2,
        },
        {
            "name": "Supabase changelog",
            "url": "https://supabase.com/changelog",
            "category": "backend_infra",
            "priority": 2,
        },
        {
            "name": "HuggingFace Daily Papers",
            "url": "https://huggingface.co/papers",
            "category": "ai_viral",
            "priority": 1,
        },
        {
            "name": "n8n changelog",
            "url": "https://docs.n8n.io/release-notes/",
            "category": "automation",
            "priority": 3,
        },
    ]

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.llm = LLMRouter(config)
        self.model = self.llm.get_model('daily')
        self._ensure_schema()

    def _ensure_schema(self):
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS infra_launches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT,
                source_category TEXT,
                primitive_name TEXT,
                announcement_date TEXT,
                url TEXT,
                summary TEXT,
                what_unlocks TEXT,
                opportunity_window_months INTEGER,
                detected_at TEXT DEFAULT (datetime('now')),
                processed INTEGER DEFAULT 0,
                UNIQUE(url, primitive_name)
            );
        """)
        self.kb.conn.commit()

    # ─── Public API ────────────────────────────────────────

    def scan_weekly(self) -> dict:
        """Scan all infra sources for new primitives from last 7 days."""
        logger.info("🔌 Aile 2: Infra launch scan starting")

        all_launches = []
        by_source = {}

        for src in self.SOURCES:
            try:
                launches = self._scan_source(src)
                all_launches.extend(launches)
                by_source[src['name']] = len(launches)
            except Exception as e:
                logger.warning(f"Infra source '{src['name']}' failed: {e}")

        logger.info(f"🔌 Aile 2 complete: {len(all_launches)} launches")
        return {
            'scan_date': datetime.utcnow().isoformat(),
            'total_launches': len(all_launches),
            'by_source': by_source,
            'launches': all_launches,
        }

    def _scan_source(self, src: dict) -> list:
        prompt = f"""Web'de ara: {src['url']} son 7-14 günde hangi yeni feature/primitive duyuruldu?

GÖREV: Bu kaynaktan 1-3 ÖNEMLİ yeni primitive/feature/API buldu. Minor bugfix'leri atla.

Önemli = "Bir şey geçen hafta yapılamazdı, bu hafta yapılabiliyor" niteliğinde.

Her yeni primitive için:
- Adı
- Duyuru tarihi
- 1-2 cümle ne yaptığı
- Neyi olanaklı kıldığı (what_unlocks): bu primitive üzerine hangi iş modeli kurulabilir?
- Fırsat penceresi (kaç ay): genellikle 6-12 ay

SADECE valid JSON (bulgu yoksa boş findings):

{{
  "findings": [
    {{
      "primitive_name": "...",
      "announcement_date": "YYYY-MM-DD",
      "url": "...",
      "summary": "1-2 cümle",
      "what_unlocks": "Bu primitive üzerine kurulabilecek iş modeli",
      "opportunity_window_months": 12
    }}
  ]
}}"""

        try:
            response = self.llm.create(
                model=self.model,
                max_tokens=1536,
                messages=[{"role": "user", "content": prompt}],
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
            )
            text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text += block.text
            parsed = self._parse_json(text)
        except Exception as e:
            logger.warning(f"Scan {src['name']} failed: {e}")
            return []

        findings = parsed.get('findings', []) if parsed else []
        stored = []
        cursor = self.kb.conn.cursor()
        for f in findings:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO infra_launches
                    (source_name, source_category, primitive_name,
                     announcement_date, url, summary, what_unlocks,
                     opportunity_window_months)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    src['name'], src['category'],
                    (f.get('primitive_name') or '')[:200],
                    f.get('announcement_date', ''),
                    (f.get('url') or '')[:500],
                    (f.get('summary') or '')[:500],
                    (f.get('what_unlocks') or '')[:500],
                    int(f.get('opportunity_window_months', 12) or 12),
                ))
                self.kb.conn.commit()
                if cursor.rowcount > 0:
                    stored.append({**f, 'source_name': src['name']})
            except Exception as e:
                logger.warning(f"Infra save failed: {e}")

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

    def get_recent(self, days: int = 14) -> list:
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            SELECT * FROM infra_launches
            WHERE detected_at >= datetime('now', '-' || ? || ' days')
            ORDER BY detected_at DESC
        """, (days,))
        return [dict(r) for r in cursor.fetchall()]
