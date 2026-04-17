"""
Wildcatter 4-Layer Output Architecture

Replaces daily digest with a 4-layer distilled output system.
Source: Open Brain → intelligence/pattern-framework (Katman A/B/C/D)

  Layer A — Dünya Tomografisi (weekly Friday)
    5-8 world-level anomalies: cost curves breaking, regulations changing,
    primitive launches, convergent complaints. Not opportunities — OBSERVATIONS.
    Feeds intuition. "Boş hafta yok."

  Layer B — Konvergans Tezleri (monthly 1st)
    1-3 theses built from 2-3 trend convergences seen across 4 weeks of Layer A.
    Not yet opportunities — precursors to opportunities. "Boş ay yok."

  Layer C — Aday Fırsatlar (quarterly)
    1-3 matured theses that survived contact with scoring/pattern/wow filters.
    Real candidates worthy of commitment. Fatih reviews manually.

  Layer D — Şimdi Hareket Et Alarmı (event-driven)
    0-2 per year. Signals so strong that waiting is losing.

Each layer distills from the one above. Signal-to-noise ratio increases
at each level. All layers stored to Open Brain.
"""

import json
import logging
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from .llm_router import LLMRouter

logger = logging.getLogger("scout.layers")


class WildcatterLayers:
    """Generate the 4 distillation layers (A/B/C/D)."""

    def __init__(self, config: dict, knowledge_base, brain_client=None,
                 pattern_matcher=None, wow_threshold=None):
        self.config = config
        self.kb = knowledge_base
        self.brain = brain_client
        self.patterns = pattern_matcher
        self.wow = wow_threshold
        self.llm = LLMRouter(config)
        # Layer A uses Gemini (cheap, fresh web), B/C/D use Claude Sonnet (reasoning)
        self.daily_model = self.llm.get_model('daily')
        self.weekly_model = self.llm.get_model('weekly')

    # ─── Layer A: Dünya Tomografisi (Weekly Friday) ────────

    def generate_layer_a(self) -> dict:
        """Generate weekly world-tomography report.

        Pulls from latest week's signals across all sources. Synthesizes
        into 5-8 anomaly observations. NOT opportunities — observations.
        """
        logger.info("🌍 Generating Layer A — Dünya Tomografisi")

        # Collect last 7 days of signals + new opportunities for context
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            SELECT type, summary, tags_json, source
            FROM signals
            WHERE created_at >= datetime('now', '-7 days')
            ORDER BY created_at DESC LIMIT 100
        """)
        recent_signals = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT title, sector, why_now, tier
            FROM opportunities
            WHERE created_at >= datetime('now', '-7 days') AND tier IN ('FIRE', 'HIGH')
            ORDER BY weighted_total DESC LIMIT 30
        """)
        recent_opps = [dict(r) for r in cursor.fetchall()]

        # Build prompt
        signals_text = "\n".join(
            f"- [{s.get('type', '?')}] {s.get('summary', '')[:200]}"
            for s in recent_signals[:50]
        )
        opps_text = "\n".join(
            f"- [{o.get('tier', '?')}] {o.get('title', '')}: {o.get('why_now', '')[:150]}"
            for o in recent_opps[:20]
        )

        prompt = f"""Sen Wildcatter'ın Layer A (Dünya Tomografisi) üreticisisin.

Görev: Geçen hafta dünyada neler oldu?
- Hangi maliyet eğrisi kırıldı?
- Hangi regülasyon değişti?
- Hangi teknolojik primitive lansmanı yapıldı?
- Hangi sektörde toplu şikayet patladı?
- Hangi anomali gözlemlendi?

Bu HAFTANIN ham sinyalleri:

YENİ OPPORTUNITIES (son 7 gün):
{opps_text}

YENİ SINYALLER (son 7 gün):
{signals_text}

Ayrıca web'de ara:
- "biggest news this week in AI / tech / fintech / biotech 2026"
- "major policy regulation change this week UK EU US"
- "cost curve break API GPU sensor logistics this week"

KURALLAR:
- Her madde 2-3 cümle
- Madde FIRSAT DEĞİL, GÖZLEM
- Spesifik olsun (şirket adı, sayı, tarih)
- İnşaat/BSA/BTR yazma (ThreadForge feed'inde var)
- Boş hafta yok — 5-8 madde bul

SADECE valid JSON döndür:

{{
  "items": [
    {{
      "category": "cost_curve|regulation|primitive|complaint|anomaly",
      "headline": "Başlık (10-15 kelime)",
      "body": "2-3 cümle detay",
      "source": "Nereden (publication / company / paper)",
      "why_matters": "Fatih için neden önemli (1 cümle)"
    }}
  ],
  "week_label": "YYYY-WW",
  "meta_note": "Bu haftaya dair genel ritim: aktif mi, durgun mu?"
}}"""

        response = self.llm.create(
            model=self.daily_model,
            max_tokens=3072,
            messages=[{"role": "user", "content": prompt}],
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
        )

        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text
        parsed = self._parse_json(text)

        report = {
            'layer': 'A',
            'type': 'tomography',
            'week_label': parsed.get('week_label') or datetime.utcnow().strftime('%Y-W%V'),
            'items': parsed.get('items', []),
            'meta_note': parsed.get('meta_note', ''),
            'generated_at': datetime.utcnow().isoformat(),
        }
        report['summary_md'] = self._format_layer_a(report)

        # Persist to Open Brain
        if self.brain:
            path = f"intelligence/tomography/{report['week_label']}"
            self._push_to_brain(path, report)

        logger.info(f"🌍 Layer A: {len(report['items'])} items")
        return report

    def _format_layer_a(self, report: dict) -> str:
        lines = [
            f"# 🌍 Dünya Tomografisi — {report['week_label']}",
            f"*Layer A · Weekly Friday output · {len(report['items'])} items*",
            "",
        ]
        if report.get('meta_note'):
            lines.append(f"> {report['meta_note']}")
            lines.append("")
        category_emoji = {
            'cost_curve': '💰',
            'regulation': '⚖️',
            'primitive': '🔌',
            'complaint': '😡',
            'anomaly': '🌀',
        }
        for i, item in enumerate(report.get('items', []), 1):
            emoji = category_emoji.get(item.get('category'), '•')
            lines.append(f"## {i}. {emoji} {item.get('headline', '?')}")
            lines.append(f"{item.get('body', '')}")
            src = item.get('source', '')
            if src:
                lines.append(f"*Kaynak:* {src}")
            if item.get('why_matters'):
                lines.append(f"*Neden:* {item['why_matters']}")
            lines.append("")
        return "\n".join(lines)

    # ─── Layer B: Konvergans Tezleri (Monthly 1st) ─────────

    def generate_layer_b(self) -> dict:
        """Generate monthly convergence theses.

        Reads last 4 weeks of Layer A tomography items, looks for 2-3
        trend convergences. Synthesizes 1-3 theses.
        """
        logger.info("🧠 Generating Layer B — Konvergans Tezleri")

        # Gather last 4 weeks of tomography items
        # TODO: when brain has a query method, use it. For now, use KB-stored items
        # Placeholder: read from a future `intelligence_events` or equivalent store
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            SELECT type, summary FROM signals
            WHERE created_at >= datetime('now', '-30 days')
            ORDER BY created_at DESC LIMIT 200
        """)
        month_signals = [dict(r) for r in cursor.fetchall()]

        signals_text = "\n".join(
            f"- [{s.get('type', '?')}] {s.get('summary', '')[:180]}"
            for s in month_signals[:80]
        )

        prompt = f"""Sen Wildcatter'ın Layer B (Konvergans Tezleri) üreticisisin.

Görev: Geçen AYIN sinyallerinden hangi 2-3 trend çakışıyor?
Tek trend fırsat değil. Üç trend aynı yöne işaret ediyorsa TEZ doğmuştur.
Tez henüz fırsat değil ama fırsat öncüsüdür.

SON 30 GÜN SİNYALLER:
{signals_text}

KURALLAR:
- 1-3 tez
- Her tez en az 3 farklı trendden beslenmeli
- Tez formülü: "X + Y + Z → önümüzdeki 12-18 ayda Q olur"
- Spesifik, test edilebilir
- Fatih'in 7 pattern'inden en az 2'sine kance atmalı

SADECE JSON:

{{
  "theses": [
    {{
      "thesis": "Tek cümle tez — test edilebilir tahmin",
      "converging_trends": ["trend 1", "trend 2", "trend 3"],
      "time_horizon": "12-18 ay",
      "why_now": "2-3 cümle",
      "implications_for_fatih": "Fatih için ne açar (2-3 cümle)",
      "pattern_hooks": ["Pattern #X", "Pattern #Y"],
      "verifiable_by": "Tezin doğru/yanlış olduğunu 6-12 ay içinde nasıl anlarız?"
    }}
  ]
}}"""

        response = self.llm.create(
            model=self.weekly_model,
            max_tokens=3072,
            messages=[{"role": "user", "content": prompt}],
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
        )

        # Multi-turn loop (Claude)
        messages = [{"role": "user", "content": prompt}]
        loops = 0
        while response.stop_reason == "tool_use" and loops < 10:
            loops += 1
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if getattr(block, 'type', None) == "tool_use":
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": "Search completed."
                    })
            messages.append({"role": "user", "content": tool_results})
            response = self.llm.create(
                model=self.weekly_model, max_tokens=3072,
                messages=messages,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
            )

        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text
        parsed = self._parse_json(text)

        report = {
            'layer': 'B',
            'type': 'theses',
            'month_label': datetime.utcnow().strftime('%Y-%m'),
            'theses': parsed.get('theses', []),
            'generated_at': datetime.utcnow().isoformat(),
        }
        report['summary_md'] = self._format_layer_b(report)

        if self.brain:
            path = f"intelligence/theses/{report['month_label']}"
            self._push_to_brain(path, report)

        logger.info(f"🧠 Layer B: {len(report['theses'])} theses")
        return report

    def _format_layer_b(self, report: dict) -> str:
        lines = [
            f"# 🧠 Konvergans Tezleri — {report['month_label']}",
            f"*Layer B · Monthly output · {len(report['theses'])} thesis*",
            "",
        ]
        for i, t in enumerate(report.get('theses', []), 1):
            lines.append(f"## Tez #{i}")
            lines.append(f"**{t.get('thesis', '?')}**")
            lines.append("")
            if t.get('converging_trends'):
                lines.append("**Çakışan trendler:**")
                for tr in t['converging_trends']:
                    lines.append(f"- {tr}")
                lines.append("")
            if t.get('why_now'):
                lines.append(f"**Neden şimdi:** {t['why_now']}")
                lines.append("")
            if t.get('implications_for_fatih'):
                lines.append(f"**Fatih için:** {t['implications_for_fatih']}")
                lines.append("")
            if t.get('pattern_hooks'):
                lines.append(f"*Pattern hook:* {', '.join(t['pattern_hooks'])}")
            if t.get('verifiable_by'):
                lines.append(f"*Doğrulama yöntemi:* {t['verifiable_by']}")
            lines.append("")
        return "\n".join(lines)

    # ─── Layer C: Aday Fırsatlar (Quarterly) ───────────────

    def generate_layer_c(self) -> dict:
        """Generate quarterly candidate opportunities from matured theses.

        Reads last quarter's Layer B theses, checks which matured into
        actionable opportunities (scored, patterns matched, wow-candidates).
        """
        logger.info("🎯 Generating Layer C — Aday Fırsatlar")

        cursor = self.kb.conn.cursor()
        # Candidates = wow_candidate pattern verdict OR VAY tier
        cursor.execute("""
            SELECT id, title, sector, one_liner, weighted_total, tier,
                   pattern_verdict, pattern_count, is_vay
            FROM opportunities
            WHERE created_at >= datetime('now', '-90 days')
              AND (pattern_verdict = 'wow_candidate' OR is_vay = 1
                   OR (tier = 'FIRE' AND pattern_count >= 4))
            ORDER BY is_vay DESC, pattern_count DESC, weighted_total DESC
            LIMIT 10
        """)
        candidates = [dict(r) for r in cursor.fetchall()]

        report = {
            'layer': 'C',
            'type': 'candidates',
            'quarter_label': self._quarter_label(),
            'candidates': candidates,
            'vay_count': sum(1 for c in candidates if c.get('is_vay')),
            'generated_at': datetime.utcnow().isoformat(),
        }
        report['summary_md'] = self._format_layer_c(report)

        if self.brain:
            path = f"intelligence/candidates/{report['quarter_label']}"
            self._push_to_brain(path, report)

        logger.info(f"🎯 Layer C: {len(candidates)} candidates, "
                    f"{report['vay_count']} VAY")
        return report

    def _format_layer_c(self, report: dict) -> str:
        lines = [
            f"# 🎯 Aday Fırsatlar — {report['quarter_label']}",
            f"*Layer C · Quarterly output · {len(report['candidates'])} candidates, "
            f"{report['vay_count']} VAY*",
            "",
        ]
        if len(report['candidates']) == 0:
            lines.append("_Bu çeyrekte aday yok. Yıllık standart: 'yıl asla boş' — "
                         "sistem kalibrasyonu gerekli olabilir._")
            return "\n".join(lines)
        for i, c in enumerate(report['candidates'], 1):
            vay_mark = "🌟 *VAY*" if c.get('is_vay') else "🎯"
            lines.append(f"## {i}. {vay_mark} {c.get('title', '?')}")
            lines.append(f"`{c.get('id', '')}` · "
                         f"{c.get('sector', '?')} · "
                         f"Score {c.get('weighted_total', 0):.0f} · "
                         f"Patterns {c.get('pattern_count', 0)}/7")
            if c.get('one_liner'):
                lines.append(f"_{c['one_liner']}_")
            lines.append("")
        return "\n".join(lines)

    # ─── Layer D: Alarm (Event-driven) ─────────────────────

    def generate_layer_d_alarm(self, trigger_event: str,
                                 related_opp_id: str = None) -> dict:
        """Generate an emergency D-layer alarm.

        Rare (0-2/year). Only when a signal is strong enough that waiting
        for the next layer would lose the window.
        """
        logger.info(f"🚨 Generating Layer D Alarm: {trigger_event[:80]}")

        related_opp = None
        if related_opp_id:
            cursor = self.kb.conn.cursor()
            cursor.execute("SELECT * FROM opportunities WHERE id = ?", (related_opp_id,))
            row = cursor.fetchone()
            related_opp = dict(row) if row else None

        alarm = {
            'layer': 'D',
            'type': 'alarm',
            'trigger': trigger_event,
            'related_opportunity_id': related_opp_id,
            'related_opportunity': related_opp,
            'generated_at': datetime.utcnow().isoformat(),
            'date_label': datetime.utcnow().strftime('%Y-%m-%d'),
        }

        if self.brain:
            path = f"intelligence/alarms/{alarm['date_label']}"
            self._push_to_brain(path, alarm)

        return alarm

    # ─── Helpers ───────────────────────────────────────────

    def _quarter_label(self) -> str:
        now = datetime.utcnow()
        q = (now.month - 1) // 3 + 1
        return f"{now.year}-Q{q}"

    def _push_to_brain(self, path: str, report: dict):
        """Push layer report to Open Brain."""
        if not self.brain:
            return
        try:
            import asyncio
            content = report.get('summary_md') or json.dumps(report, ensure_ascii=False, indent=2)
            asyncio.create_task(self.brain._ingest({
                "path": path,
                "content": content,
                "metadata": {
                    "source": "wildcatter_layers",
                    "layer": report.get('layer'),
                    "type": report.get('type'),
                }
            }))
        except Exception as e:
            logger.warning(f"Brain push failed ({path}): {e}")

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
