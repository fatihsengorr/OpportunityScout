"""
Wildcatter Faz 4 — Monthly Scorer Drift Audit

Source: Open Brain → intelligence/wildcatter/insights (Hassabis)

Risk: LLM scorer zamanla "bir paterne" düşer — prompt'ta boşluk bulur,
aynı tip fırsatları sistematik olarak yüksek skorlar.

Çözüm: Her ay Claude Opus ile "son 30 günün top 20 fırsatı rastgele mi
yoksa belli bir paterne mi düşüyor?" audit'i.

Output → Open Brain `intelligence/audits/YYYY-MM-scorer`
Drift tespit edilirse → Telegram alarmı + prompt review notu.
"""

import json
import logging
from datetime import datetime
from .llm_router import LLMRouter

logger = logging.getLogger("scout.scorer_audit")


class ScorerAudit:
    """Monthly audit of scorer behavior for drift detection."""

    def __init__(self, config: dict, knowledge_base, brain_client=None):
        self.config = config
        self.kb = knowledge_base
        self.brain = brain_client
        self.llm = LLMRouter(config)
        # Audit uses the weekly model (Claude Sonnet) — Opus overkill for this
        self.model = self.llm.get_model('weekly')
        self._ensure_schema()

    def _ensure_schema(self):
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scorer_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_month TEXT NOT NULL,
                drift_detected INTEGER DEFAULT 0,
                drift_category TEXT,
                audit_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(audit_month)
            );
        """)
        self.kb.conn.commit()

    def run_monthly_audit(self) -> dict:
        """Analyze last 30 days of top opportunities for pattern drift."""
        logger.info("🔎 Scorer audit starting")

        month = datetime.utcnow().strftime('%Y-%m')

        # Gather last 30 days' top 20 opportunities
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            SELECT id, title, sector, tier, weighted_total,
                   pattern_count, pattern_verdict
            FROM opportunities
            WHERE created_at >= datetime('now', '-30 days')
            ORDER BY weighted_total DESC LIMIT 20
        """)
        top20 = [dict(r) for r in cursor.fetchall()]

        if len(top20) < 5:
            logger.info("🔎 Not enough data for audit (< 5 opps)")
            return {'status': 'insufficient_data', 'count': len(top20)}

        # Build audit prompt
        opps_text = "\n".join(
            f"{i+1}. [{o['tier']} {o['weighted_total']:.0f}] "
            f"{o.get('sector', '?')}: {o['title'][:80]} "
            f"(P{o.get('pattern_count', 0)}/7)"
            for i, o in enumerate(top20)
        )

        prompt = f"""Sen bir scorer drift denetçisisin. Aşağıdaki son 30 günün top 20 fırsatı
rastgele mi, yoksa scorer belli bir paterne mi düşüyor?

SON 30 GÜN TOP 20 FIRSAT:
{opps_text}

DENETİM SORULARI:
1. Sektör konsantrasyonu: Belirli bir sektörde (örn: inşaat, fintech) aşırı yoğunluk var mı?
2. Kelime motifleri: "Cross-border", "AI-powered", "compliance" gibi motifler aşırı tekrar ediyor mu?
3. Skor enflasyonu: 125+ skor alan fırsatlar çok fazla mı? (Sağlıklı oran: %10-20)
4. Pattern bias: Aynı 2-3 pattern sürekli tetikleniyor mu?
5. Gürültü vs sinyal: Fırsatlar gerçekten "vay" düzeyinde mi, yoksa jenerik mi?

SADECE valid JSON döndür:

{{
  "drift_detected": true | false,
  "drift_category": "sector_concentration|keyword_drift|score_inflation|pattern_bias|generic_noise|none",
  "sector_distribution": {{"construction": 0.35, "fintech": 0.15, ...}},
  "keyword_frequency": {{"cross-border": 8, "ai-powered": 12, "compliance": 10}},
  "score_distribution": {{"125_plus": 0.25, "100_124": 0.50, "under_100": 0.25}},
  "pattern_bias": {{"most_frequent_patterns": [3, 5], "frequency_pct": 0.70}},
  "verdict": "3-4 cümle — scorer sağlıklı mı, drift var mı?",
  "recommendations": ["Specific recommendation 1", "..."]
}}"""

        try:
            response = self.llm.create(
                model=self.model,
                max_tokens=2048,
                system="You are a strict audit analyst. Return only JSON.",
                messages=[{"role": "user", "content": prompt}],
            )
            text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text += block.text
            audit = self._parse_json(text)
        except Exception as e:
            logger.error(f"Audit LLM failed: {e}")
            return {'status': 'error', 'error': str(e)}

        if not audit:
            return {'status': 'parse_error'}

        # Persist audit
        cursor.execute("""
            INSERT OR REPLACE INTO scorer_audits
            (audit_month, drift_detected, drift_category, audit_json)
            VALUES (?, ?, ?, ?)
        """, (
            month,
            1 if audit.get('drift_detected') else 0,
            audit.get('drift_category', 'none'),
            json.dumps(audit, ensure_ascii=False),
        ))
        self.kb.conn.commit()

        # Push to Open Brain
        if self.brain:
            path = f"intelligence/audits/{month}-scorer"
            summary_md = self._format_audit_md(audit, top20)
            try:
                import asyncio
                asyncio.create_task(self.brain._ingest({
                    "path": path,
                    "content": summary_md,
                    "metadata": {
                        "source": "scorer_audit",
                        "month": month,
                        "drift_detected": audit.get('drift_detected'),
                    }
                }))
            except Exception as e:
                logger.warning(f"Audit brain push failed: {e}")

        result = {
            'status': 'complete',
            'month': month,
            'drift_detected': audit.get('drift_detected', False),
            'drift_category': audit.get('drift_category'),
            'verdict': audit.get('verdict', ''),
            'recommendations': audit.get('recommendations', []),
            'audit': audit,
        }

        if audit.get('drift_detected'):
            logger.warning(
                f"🔎 DRIFT DETECTED: {audit.get('drift_category')} — "
                f"{audit.get('verdict', '')[:200]}"
            )
        else:
            logger.info(f"🔎 Audit clean: no drift detected")

        return result

    def _format_audit_md(self, audit: dict, top20: list) -> str:
        lines = [
            f"# Scorer Audit — {datetime.utcnow().strftime('%Y-%m')}",
            f"*Drift: {'⚠️ DETECTED' if audit.get('drift_detected') else '✅ Clean'}*",
            "",
            "## Verdict",
            audit.get('verdict', '_no verdict_'),
            "",
        ]

        if audit.get('sector_distribution'):
            lines.append("## Sector Distribution")
            for sec, pct in (audit['sector_distribution'] or {}).items():
                lines.append(f"- {sec}: {pct*100:.0f}%")
            lines.append("")

        if audit.get('keyword_frequency'):
            lines.append("## Keyword Frequency")
            for kw, cnt in (audit['keyword_frequency'] or {}).items():
                lines.append(f"- `{kw}`: {cnt}")
            lines.append("")

        if audit.get('pattern_bias'):
            pb = audit['pattern_bias']
            lines.append("## Pattern Bias")
            lines.append(f"Most frequent: {pb.get('most_frequent_patterns')}, "
                         f"combined {pb.get('frequency_pct', 0)*100:.0f}% of top 20")
            lines.append("")

        if audit.get('recommendations'):
            lines.append("## Recommendations")
            for r in audit['recommendations']:
                lines.append(f"- {r}")
            lines.append("")

        lines.append("## Top 20 Audited")
        for i, o in enumerate(top20, 1):
            lines.append(
                f"{i}. [{o['tier']} {o['weighted_total']:.0f}] "
                f"{o.get('sector', '?')}: {o['title'][:80]}"
            )

        return "\n".join(lines)

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
