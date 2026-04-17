"""
OpportunityScout — Financial Modeler

For FIRE/HIGH opportunities, generate unit economics and 12-month projections:
- Revenue model identification
- Pricing tier recommendation (from sector benchmarks)
- CAC estimate (by buyer segment)
- Break-even month calculation
- 12-month projection (pessimist / realistic / optimist)
- Capital requirements (MVP + first 6 months)

Claude Sonnet generates the model, then Python does the arithmetic.
Structured output is saved and rendered as a financial summary card.
"""

import json
import logging
import yaml
from datetime import datetime
from pathlib import Path
from .llm_router import LLMRouter

logger = logging.getLogger("scout.finance")

BENCHMARKS_PATH = Path("./config/financial_benchmarks.yaml")
FOUNDER_PROFILE_PATH = Path("./config/founder_profile.yaml")


class FinancialModeler:
    """Generate unit economics and financial projections for opportunities."""

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.llm = LLMRouter(config)
        self.model = self.llm.get_model('scoring')  # Claude Sonnet

        # Load benchmarks
        self.benchmarks = self._load_yaml(BENCHMARKS_PATH)
        self._founder_profile = self._load_text(FOUNDER_PROFILE_PATH)

        # Ensure schema has finance column
        self._ensure_schema()

    def _load_yaml(self, path: Path) -> dict:
        try:
            return yaml.safe_load(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            logger.warning(f"Benchmarks file missing: {path}")
            return {}

    def _load_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return ""

    def _ensure_schema(self):
        cursor = self.kb.conn.cursor()
        cursor.execute("PRAGMA table_info(opportunities)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'finance_json' not in columns:
            cursor.execute("ALTER TABLE opportunities ADD COLUMN finance_json TEXT")
            cursor.execute("ALTER TABLE opportunities ADD COLUMN finance_generated_at TEXT")
            self.kb.conn.commit()

    # ─── Public API ─────────────────────────────────────────

    def model_opportunity(self, opp_id: str) -> dict:
        """Build a financial model for a single opportunity.

        Returns dict with:
          - revenue_model, pricing, cac, unit_economics
          - projections: {pessimist, realistic, optimist} each with monthly_revenue list
          - break_even_month, capital_required_gbp, payback_period_months
          - risk_flags: list of assumptions that could break the model
        """
        logger.info(f"💰 Modeling finances for {opp_id}...")

        cursor = self.kb.conn.cursor()
        cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Opportunity {opp_id} not found")
        opp = dict(row)

        # Phase 1: Claude reasons about model structure (no arithmetic)
        structure = self._reason_structure(opp)
        if structure.get('_parse_error'):
            return structure

        # Phase 2: Python computes unit economics + projections
        computed = self._compute_projections(structure)

        # Merge structure + computed
        model = {**structure, **computed,
                 'generated_at': datetime.utcnow().isoformat(),
                 'currency': 'GBP'}

        # Save
        self._save(opp_id, model)

        logger.info(
            f"💰 Model complete for {opp_id}: "
            f"break-even month {model.get('break_even_month', '?')}, "
            f"capital needed £{model.get('capital_required_gbp', 0):,.0f}"
        )
        return model

    # ─── Phase 1: Claude reasoning ──────────────────────────

    def _reason_structure(self, opp: dict) -> dict:
        """Claude Sonnet reasons about business model structure.

        Returns JSON with chosen revenue model, target segment, pricing,
        churn, expected ARPU, growth rate assumptions. No math.
        """
        # Prep benchmark context (compact)
        rev_models = list((self.benchmarks.get('revenue_models') or {}).keys())
        cac_segments = list((self.benchmarks.get('cac_benchmarks') or {}).keys())

        prompt = f"""Sen deneyimli bir erken aşama finansal modelcisisin. Bir iş fırsatı için unit economics varsayımlarını çıkaracaksın.

FIRSAT:
Title: {opp.get('title', '?')}
One-liner: {opp.get('one_liner', '')}
Sektör: {opp.get('sector', '?')}
Revenue Path: {opp.get('revenue_path', '')}
First Move: {opp.get('first_move', '')}
Tier: {opp.get('tier', '?')}

FOUNDER CONTEXT:
{self._founder_profile[:1200]}

AVAILABLE REVENUE MODELS (choose one): {', '.join(rev_models)}
AVAILABLE CAC SEGMENTS (choose one): {', '.join(cac_segments)}

GÖREV: Aşağıdaki JSON'u doldur. Sadece valid JSON döndür, başka metin yok.

{{
  "revenue_model": "choose one from AVAILABLE REVENUE MODELS",
  "revenue_model_justification": "1 cümle — bu model neden en mantıklı",

  "target_segment": "choose one from AVAILABLE CAC SEGMENTS",
  "target_segment_justification": "1 cümle — hedef müşteri kim",

  "pricing_gbp": {{
    "tier_low": {{"price": 0, "unit": "per month / per project / one-time", "description": "..."}},
    "tier_standard": {{"price": 0, "unit": "...", "description": "..."}},
    "tier_high": {{"price": 0, "unit": "...", "description": "..."}}
  }},

  "arpu_assumption_gbp": 0,
  "arpu_justification": "Expected blended ARPU assuming most customers at 'standard' tier",

  "monthly_churn_rate": 0.0,
  "churn_justification": "1 cümle",

  "growth_assumptions": {{
    "pessimist": {{"new_customers_month_1": 0, "monthly_growth_pct": 0, "note": "worst-case"}},
    "realistic": {{"new_customers_month_1": 0, "monthly_growth_pct": 0, "note": "base case"}},
    "optimist": {{"new_customers_month_1": 0, "monthly_growth_pct": 0, "note": "best case"}}
  }},

  "variable_cost_per_customer_gbp": 0,
  "variable_cost_justification": "API costs, hosting, fulfillment per customer",

  "fixed_monthly_costs_gbp": {{
    "infrastructure": 0,
    "tools": 0,
    "founder_draw": 0,
    "marketing": 0,
    "other": 0
  }},

  "mvp_capital_gbp": 0,
  "mvp_capital_justification": "One-time cost to launch",

  "key_risks": [
    "Varsayım 1 — eğer bu yanlışsa model kırılır",
    "Varsayım 2",
    "Varsayım 3"
  ]
}}

KURALLAR:
- Founder'ın Turkish manufacturing + UK entity + IT background avantajını hesaba kat (düşük maliyet)
- Pricing için sektör gerçeklerine uy (SMB SaaS £49-199, productized service £500-5000 vs)
- Pessimist ≤ realistic ≤ optimist olmalı
- Realistic senaryo "sector benchmark standard"ı olmalı
- All values GBP (£) — dolar değil"""

        response = self.llm.create(
            model=self.model,
            max_tokens=2048,
            system="You are a rigorous early-stage financial modeler. Return only valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text
        return self._parse_json(text)

    # ─── Phase 2: Python arithmetic ─────────────────────────

    def _compute_projections(self, s: dict) -> dict:
        """Compute 12-month projections from structure assumptions.

        Deterministic math — not LLM.
        """
        try:
            arpu = float(s.get('arpu_assumption_gbp', 0))
            churn = float(s.get('monthly_churn_rate', 0))
            var_cost = float(s.get('variable_cost_per_customer_gbp', 0))

            fixed = s.get('fixed_monthly_costs_gbp', {}) or {}
            fixed_total = sum(float(fixed.get(k, 0) or 0)
                              for k in ['infrastructure', 'tools', 'founder_draw',
                                        'marketing', 'other'])

            mvp_capital = float(s.get('mvp_capital_gbp', 0))

            # Gross margin
            rev_model = s.get('revenue_model')
            bench = (self.benchmarks.get('revenue_models') or {}).get(rev_model, {})
            gross_margin = bench.get('typical_gross_margin', 0.5)

            # CAC
            target = s.get('target_segment')
            cac_data = (self.benchmarks.get('cac_benchmarks') or {}).get(target, {})
            cac = cac_data.get('typical_cac_gbp', 500)

            # Unit economics
            ltv = arpu * gross_margin / churn if churn > 0 else arpu * gross_margin * 36
            ltv_cac_ratio = ltv / cac if cac > 0 else 0
            payback_months = cac / (arpu * gross_margin) if arpu > 0 and gross_margin > 0 else 999

            # 3 scenarios
            scenarios = {}
            growth = s.get('growth_assumptions', {}) or {}
            for scenario_name in ('pessimist', 'realistic', 'optimist'):
                g = growth.get(scenario_name, {}) or {}
                new_m1 = float(g.get('new_customers_month_1', 0))
                growth_pct = float(g.get('monthly_growth_pct', 0)) / 100.0

                monthly_revenue = []
                monthly_customers = []
                monthly_net = []
                cumulative_cash = -mvp_capital
                cumulative_cash_list = []
                active_customers = 0.0
                break_even_month = None
                cash_trough = 0.0

                for m in range(1, 13):
                    new_customers = new_m1 * ((1 + growth_pct) ** (m - 1))
                    churned = active_customers * churn
                    active_customers = active_customers - churned + new_customers
                    revenue = active_customers * arpu
                    variable_costs = active_customers * var_cost
                    acquisition_cost = new_customers * cac
                    gross_profit = revenue - variable_costs
                    net_profit = gross_profit - fixed_total - acquisition_cost

                    monthly_revenue.append(round(revenue, 2))
                    monthly_customers.append(round(active_customers, 1))
                    monthly_net.append(round(net_profit, 2))
                    cumulative_cash += net_profit
                    cumulative_cash_list.append(round(cumulative_cash, 2))
                    cash_trough = min(cash_trough, cumulative_cash)

                    if break_even_month is None and revenue >= fixed_total + variable_costs:
                        break_even_month = m

                scenarios[scenario_name] = {
                    'monthly_revenue': monthly_revenue,
                    'monthly_customers': monthly_customers,
                    'monthly_net_profit': monthly_net,
                    'cumulative_cash': cumulative_cash_list,
                    'final_mrr_gbp': round(monthly_revenue[-1], 0),
                    'final_customers': round(monthly_customers[-1], 0),
                    'break_even_month': break_even_month,
                    'cash_trough_gbp': round(cash_trough, 0),
                    'capital_required_gbp': round(abs(cash_trough) + mvp_capital, 0),
                }

            realistic = scenarios['realistic']

            return {
                'unit_economics': {
                    'arpu_gbp': round(arpu, 2),
                    'gross_margin': round(gross_margin, 2),
                    'cac_gbp': round(cac, 0),
                    'ltv_gbp': round(ltv, 0),
                    'ltv_cac_ratio': round(ltv_cac_ratio, 1),
                    'payback_months': round(payback_months, 1),
                    'monthly_churn_rate': round(churn, 3),
                    'fixed_monthly_costs_gbp': round(fixed_total, 0),
                    'variable_cost_per_customer_gbp': round(var_cost, 2),
                },
                'projections': scenarios,
                'break_even_month': realistic.get('break_even_month'),
                'capital_required_gbp': realistic.get('capital_required_gbp'),
                'verdict': self._verdict(ltv_cac_ratio, payback_months,
                                         realistic.get('break_even_month')),
            }
        except Exception as e:
            logger.error(f"Projection compute failed: {e}")
            return {'_compute_error': str(e)}

    def _verdict(self, ltv_cac: float, payback: float,
                 break_even: int) -> str:
        """Simple heuristic verdict."""
        if ltv_cac >= 3 and payback <= 12 and break_even and break_even <= 9:
            return "STRONG_ECONOMICS"
        if ltv_cac >= 3 and payback <= 18:
            return "VIABLE"
        if ltv_cac >= 1 and payback <= 24:
            return "MARGINAL"
        return "WEAK_ECONOMICS"

    # ─── Storage + Rendering ────────────────────────────────

    def _save(self, opp_id: str, model: dict):
        cursor = self.kb.conn.cursor()
        cursor.execute("""
            UPDATE opportunities
            SET finance_json = ?,
                finance_generated_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = ?
        """, (json.dumps(model, ensure_ascii=False), opp_id))
        self.kb.conn.commit()

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
        logger.error(f"Finance JSON parse failed: {text[:200]}")
        return {"_parse_error": True, "_raw": text[:2000]}

    def format_summary(self, opp: dict, model: dict) -> str:
        """Human-readable summary for Telegram/email."""
        if model.get('_parse_error') or model.get('_compute_error'):
            return f"❌ Financial model failed: {model.get('_compute_error') or 'parse error'}"

        ue = model.get('unit_economics', {})
        realistic = model.get('projections', {}).get('realistic', {})
        pess = model.get('projections', {}).get('pessimist', {})
        opt = model.get('projections', {}).get('optimist', {})

        verdict_emoji = {
            'STRONG_ECONOMICS': '🟢',
            'VIABLE': '🟡',
            'MARGINAL': '🟠',
            'WEAK_ECONOMICS': '🔴',
        }.get(model.get('verdict', ''), '⚪')

        lines = [
            f"💰 *Financial Model — {opp.get('title', '?')}*",
            f"`{opp.get('id', '?')}` · {verdict_emoji} *{model.get('verdict', '?')}*",
            "",
            f"📋 *Revenue Model:* {model.get('revenue_model', '?')}",
            f"🎯 *Target:* {model.get('target_segment', '?')}",
            "",
            "*Unit Economics:*",
            f"• ARPU: £{ue.get('arpu_gbp', 0):.0f}/mo",
            f"• CAC: £{ue.get('cac_gbp', 0):.0f}",
            f"• LTV: £{ue.get('ltv_gbp', 0):.0f}",
            f"• LTV/CAC: {ue.get('ltv_cac_ratio', 0):.1f}x",
            f"• Payback: {ue.get('payback_months', 0):.1f} months",
            f"• Gross margin: {ue.get('gross_margin', 0)*100:.0f}%",
            f"• Monthly fixed costs: £{ue.get('fixed_monthly_costs_gbp', 0):.0f}",
            "",
            "*12-Month Projection (realistic):*",
            f"• Customers @ Y1: {realistic.get('final_customers', 0):.0f}",
            f"• MRR @ Y1: £{realistic.get('final_mrr_gbp', 0):,.0f}",
            f"• Break-even: month {realistic.get('break_even_month', '—')}",
            f"• Capital required: £{realistic.get('capital_required_gbp', 0):,.0f}",
            "",
            "*Scenario Range (MRR @ Month 12):*",
            f"• Pessimist: £{pess.get('final_mrr_gbp', 0):,.0f}",
            f"• Realistic: £{realistic.get('final_mrr_gbp', 0):,.0f}",
            f"• Optimist:  £{opt.get('final_mrr_gbp', 0):,.0f}",
        ]

        risks = model.get('key_risks', [])
        if risks:
            lines.append("")
            lines.append("*⚠️ Assumption Risks:*")
            for r in risks[:4]:
                lines.append(f"• {r}")

        return "\n".join(lines)
