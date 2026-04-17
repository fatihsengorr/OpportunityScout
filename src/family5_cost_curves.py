"""
Wildcatter Aile 5 — Maliyet Eğrileri Tracker

Tracks 15+ key cost metrics: API prices, hardware, sensors, logistics (Drewry),
commodities. When a metric drops ≥20%, an opportunity window opens — this
feeds Layer A tomography.

Philosophy: "A thing that wasn't economic last year is economic this year.
The opportunity window just opened." (Open Brain, wildcatter/sources Aile 5)

Metrics live in config/cost_curves.yaml with baseline + current values.
Weekly: fetch updates, compute deltas, detect correlations, emit signals.

Current implementation: LLM-assisted web fetch (no paid data APIs).
Future: direct API integration with Drewry, commodity feeds.
"""

import json
import logging
import yaml
from datetime import datetime
from pathlib import Path
from .llm_router import LLMRouter

logger = logging.getLogger("scout.family5")

CURVES_PATH = Path("./config/cost_curves.yaml")


class CostCurvesTracker:
    """Track cost curves weekly; emit signals on breakouts."""

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.llm = LLMRouter(config)
        self.model = self.llm.get_model('daily')  # Gemini with Google Search
        self.curves_config = self._load_curves()
        self._ensure_schema()

    def _load_curves(self) -> dict:
        try:
            return yaml.safe_load(CURVES_PATH.read_text(encoding='utf-8'))
        except FileNotFoundError:
            logger.error(f"cost_curves.yaml missing")
            return {"metrics": [], "alert_rules": {}}

    def _ensure_schema(self):
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cost_curve_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_id TEXT NOT NULL,
                metric_name TEXT,
                category TEXT,
                observed_value REAL,
                baseline_value REAL,
                delta_pct REAL,
                observed_at TEXT DEFAULT (datetime('now')),
                source_note TEXT,
                UNIQUE(metric_id, observed_at)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cost_curve_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_type TEXT,
                metric_id TEXT,
                headline TEXT,
                detail TEXT,
                detected_at TEXT DEFAULT (datetime('now')),
                processed INTEGER DEFAULT 0
            );
        """)
        self.kb.conn.commit()

    # ─── Public API ────────────────────────────────────────

    def scan_weekly(self) -> dict:
        """Check all metrics, detect signals, return summary."""
        logger.info("💰 Aile 5: Cost curve weekly scan starting")

        metrics = self.curves_config.get('metrics', [])
        updates = []

        for metric in metrics:
            if metric.get('check_frequency', 'weekly') != 'weekly':
                # Skip non-weekly for this scan (quarterly/monthly tracked separately)
                continue
            try:
                updated = self._fetch_single_metric(metric)
                if updated:
                    updates.append(updated)
            except Exception as e:
                logger.warning(f"Cost metric {metric['id']} failed: {e}")

        # Detect signals
        signals = self._detect_signals(updates)
        correlations = self._check_correlations(updates)

        logger.info(f"💰 Cost scan: {len(updates)} updates, "
                    f"{len(signals)} signals, {len(correlations)} correlations")

        # Synthesize for Layer A (if any signals)
        synthesis = None
        if signals or correlations:
            synthesis = self._synthesize(updates, signals, correlations)

        return {
            'scan_date': datetime.utcnow().isoformat(),
            'metrics_checked': len(updates),
            'signals': signals,
            'correlations': correlations,
            'synthesis': synthesis,
        }

    # ─── Single metric fetch ───────────────────────────────

    def _fetch_single_metric(self, metric: dict) -> dict:
        """Use web search to fetch latest value for a metric.

        We rely on LLM grounding rather than paid data APIs — good enough
        for detecting ≥20% moves, not high-frequency trading.
        """
        name = metric['name']
        prompt = f"""Web'de ara: "{name} current price April 2026"

GÖREV: Bu metrik için GÜNCEL piyasa değerini bul ve return et.

Eğer bulabilirsen:
- Son bilinen değeri (sayısal, birim ile)
- Tarihi (ne kadar yakın)
- Kaynağını

Bulamazsan veya emin değilsen: "unknown" döndür.

SADECE valid JSON:
{{
  "found": true | false,
  "value": 2.50,
  "unit": "USD per 1M tokens",
  "as_of": "2026-04-15",
  "source": "OpenAI pricing page",
  "confidence": 0.9
}}"""

        try:
            response = self.llm.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
            )
            text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text += block.text
            parsed = self._parse_json(text)
        except Exception as e:
            logger.warning(f"Fetch failed for {metric['id']}: {e}")
            return None

        if not parsed or not parsed.get('found'):
            return None

        try:
            observed = float(parsed['value'])
        except (ValueError, TypeError, KeyError):
            return None

        baseline = float(metric.get('current_usd', metric.get('baseline_usd', 0)))
        if baseline <= 0:
            return None

        delta_pct = ((observed - baseline) / baseline) * 100

        # Persist to history
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO cost_curve_history
            (metric_id, metric_name, category, observed_value, baseline_value,
             delta_pct, source_note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            metric['id'], metric['name'], metric.get('category'),
            observed, baseline, delta_pct,
            parsed.get('source', '')
        ))
        self.kb.conn.commit()

        return {
            'metric_id': metric['id'],
            'metric_name': metric['name'],
            'category': metric.get('category'),
            'previous_value': baseline,
            'current_value': observed,
            'delta_pct': delta_pct,
            'as_of': parsed.get('as_of'),
            'source': parsed.get('source'),
            'bidirectional': metric.get('alert_both_directions', False),
        }

    # ─── Signal detection ──────────────────────────────────

    def _detect_signals(self, updates: list) -> list:
        """Detect price-drop signals per metric."""
        rules = self.curves_config.get('alert_rules', {})
        drop_threshold = rules.get('price_drop_threshold_pct', 20)
        rise_threshold = rules.get('price_rise_threshold_pct', 25)

        signals = []
        for u in updates:
            delta = u['delta_pct']
            if delta <= -drop_threshold:
                signals.append({
                    'type': 'price_drop',
                    'metric_id': u['metric_id'],
                    'metric_name': u['metric_name'],
                    'delta_pct': round(delta, 1),
                    'current_value': u['current_value'],
                    'previous_value': u['previous_value'],
                    'headline': f"{u['metric_name']}: %{abs(delta):.0f} DÜŞÜŞ",
                })
                self._save_signal('price_drop', u['metric_id'],
                                  f"{u['metric_name']} düştü %{abs(delta):.0f}",
                                  json.dumps(u))
            elif u.get('bidirectional') and delta >= rise_threshold:
                signals.append({
                    'type': 'price_rise',
                    'metric_id': u['metric_id'],
                    'metric_name': u['metric_name'],
                    'delta_pct': round(delta, 1),
                    'current_value': u['current_value'],
                    'previous_value': u['previous_value'],
                    'headline': f"{u['metric_name']}: %{delta:.0f} YÜKSELİŞ",
                })
                self._save_signal('price_rise', u['metric_id'],
                                  f"{u['metric_name']} yükseldi %{delta:.0f}",
                                  json.dumps(u))
        return signals

    def _check_correlations(self, updates: list) -> list:
        """Check configured correlation alarms."""
        corr_rules = self.curves_config.get('alert_rules', {}).get('correlation_alarms', [])
        by_id = {u['metric_id']: u for u in updates}
        fired = []

        for rule in corr_rules:
            trigger = rule.get('trigger', '')
            # Simple parser: "metric_id DOWN N% AND metric_id DOWN N%"
            conditions = [c.strip() for c in trigger.split(' AND ')]
            all_met = True
            for cond in conditions:
                parts = cond.split()
                if len(parts) < 3:
                    continue
                mid = parts[0]
                direction = parts[1]
                # "DOWN 15%" or "DOWN 20%"
                try:
                    pct = float(parts[2].rstrip('%'))
                except ValueError:
                    pct = 0
                u = by_id.get(mid)
                if not u:
                    all_met = False
                    break
                if direction == 'DOWN' and u['delta_pct'] > -pct:
                    all_met = False
                    break
                if direction == 'UP' and u['delta_pct'] < pct:
                    all_met = False
                    break
                if direction == 'STABLE' and abs(u['delta_pct']) > 10:
                    all_met = False
                    break
            if all_met:
                fired.append({
                    'name': rule.get('name'),
                    'trigger': trigger,
                    'implication': rule.get('implication'),
                })
                self._save_signal('correlation', rule.get('name'),
                                  rule.get('implication'), json.dumps(rule))

        return fired

    def _save_signal(self, signal_type: str, metric_id: str,
                      headline: str, detail: str):
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            INSERT INTO cost_curve_signals
            (signal_type, metric_id, headline, detail)
            VALUES (?, ?, ?, ?)
        """, (signal_type, metric_id, headline, detail))
        self.kb.conn.commit()

    # ─── Synthesis ─────────────────────────────────────────

    def _synthesize(self, updates: list, signals: list, correlations: list) -> dict:
        """LLM synthesis of cost signals into opportunity hints."""
        if not signals and not correlations:
            return None

        changes_text = "\n".join(
            f"- [{s.get('type')}] {s.get('headline')}: Δ{s.get('delta_pct')}%"
            for s in signals
        )
        corr_text = "\n".join(
            f"- {c['name']}: {c['implication']}"
            for c in correlations
        )

        template = self.curves_config.get('synthesis', {}).get('template', '')
        prompt = template.format(
            changes=changes_text or "(no major changes)",
            correlations=corr_text or "(no correlations triggered)"
        )

        try:
            response = self.llm.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text += block.text
            return self._parse_json(text)
        except Exception as e:
            logger.warning(f"Synthesis failed: {e}")
            return None

    # ─── Helpers ───────────────────────────────────────────

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

    # ─── Query interface ──────────────────────────────────

    def get_recent_signals(self, days: int = 7) -> list:
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            SELECT * FROM cost_curve_signals
            WHERE detected_at >= datetime('now', '-' || ? || ' days')
            ORDER BY detected_at DESC
        """, (days,))
        return [dict(r) for r in cursor.fetchall()]
