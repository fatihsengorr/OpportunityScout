"""
OpportunityScout — Action Kit Generator

For FIRE/HIGH opportunities, generate a complete action kit:
1. 30-day action plan (weekly milestones)
2. Customer discovery questions (10-15 validation questions)
3. Cold outreach template (for first potential customers)
4. Landing page copy (hero + 3 value props + CTA)
5. Competitor analysis checklist

Uses Claude Sonnet with focused prompt. Output saved to KB and emailed as HTML.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from .llm_router import LLMRouter

logger = logging.getLogger("scout.action_kit")

FOUNDER_PROFILE_PATH = Path("./config/founder_profile.yaml")
SYSTEM_PROMPT_PATH = Path("./SYSTEM_PROMPT.md")


class ActionKitGenerator:
    """Generate actionable startup toolkits for promising opportunities."""

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.llm = LLMRouter(config)
        # Use scoring/weekly model (Claude Sonnet) for quality reasoning
        self.model = self.llm.get_model('scoring')
        self._founder_profile = self._load_file(FOUNDER_PROFILE_PATH)
        self._system_prompt = self._load_file(SYSTEM_PROMPT_PATH)

    def _load_file(self, path: Path) -> str:
        try:
            return path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return ""

    def generate(self, opp_id: str) -> dict:
        """Generate action kit for a specific opportunity.

        Returns dict with keys:
          - plan_30day: list of weekly milestones
          - discovery_questions: list of customer interview questions
          - cold_outreach: dict with subject + body + signoff
          - landing_copy: dict with hero_headline, value_props (3), cta
          - competitor_checklist: list of items to check for each competitor
          - _raw_response: Claude's full response (for debugging)
        """
        logger.info(f"🎬 Generating action kit for {opp_id}...")

        # Fetch opportunity details
        cursor = self.kb.conn.cursor()
        cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Opportunity {opp_id} not found")
        opp = dict(row)

        # Build focused prompt
        prompt = self._build_prompt(opp)

        # Call Claude Sonnet (no web search — pure reasoning)
        response = self.llm.create(
            model=self.model,
            max_tokens=4096,
            system=self._system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text
        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text

        # Parse JSON
        kit = self._parse_kit(text)

        # Save to KB
        self._save_to_kb(opp_id, kit)

        logger.info(f"🎬 Action kit generated for {opp_id} "
                    f"({len(kit.get('plan_30day', []))} milestones, "
                    f"{len(kit.get('discovery_questions', []))} questions)")

        return kit

    def _build_prompt(self, opp: dict) -> str:
        """Build a focused prompt for action kit generation."""
        title = opp.get('title', 'Unknown')
        one_liner = opp.get('one_liner', '')
        sector = opp.get('sector', 'unknown')
        why_now = opp.get('why_now', '')
        first_move = opp.get('first_move', '')
        revenue_path = opp.get('revenue_path', '')

        return f"""Sen bir serial founder'sın. Aşağıdaki fırsat için 30-günlük bir "başlangıç kiti" oluşturacaksın.

FIRSAT: {title}
Bir cümle: {one_liner}
Sektör: {sector}
Neden şimdi: {why_now}
İlk hamle: {first_move}
Gelir yolu: {revenue_path}

FOUNDER PROFILE:
{self._founder_profile[:2000]}

Görevin: Bu fırsat için bir solo kurucunun ilk 30 günde yapacağı **somut, yürütülebilir** kit üret. Vague değil — şirket ismi, takvim, cümle. Türkçe veya İngilizce olabilir, hangisi sektör için doğalsa.

ÇIKTI: Sadece geçerli bir JSON objesi. Başka metin yok. Format:

{{
  "plan_30day": [
    {{"week": 1, "theme": "Market Validation", "tasks": ["task 1 with concrete deliverable", "task 2", ...]}},
    {{"week": 2, "theme": "...", "tasks": [...]}},
    {{"week": 3, "theme": "...", "tasks": [...]}},
    {{"week": 4, "theme": "...", "tasks": [...]}}
  ],
  "discovery_questions": [
    "Müşteri ile yapılacak 10-15 spesifik açık uçlu soru. 'Bu özelliği ister misiniz' DEĞİL. 'Son 3 ay içinde X problemi için ne kadar harcadınız?' gibi kanıt toplayan sorular."
  ],
  "cold_outreach": {{
    "target_persona": "Kime gönderilecek (pozisyon + sektör)",
    "channel": "LinkedIn DM / Email / Direct call",
    "subject": "Email subject veya LinkedIn connection note",
    "body": "Tam mesaj — kişisel, kısa (60-80 kelime), soru ile biter",
    "followup_cadence": "Yanıt gelmezse ne zaman tekrar denesin"
  }},
  "landing_copy": {{
    "hero_headline": "10-12 kelimeli güçlü başlık",
    "subheadline": "20-25 kelime — problemi ve çözümü netleştir",
    "value_props": [
      {{"icon": "⚡", "title": "3-5 kelime", "description": "Bir cümle açıklama"}},
      {{"icon": "🔒", "title": "...", "description": "..."}},
      {{"icon": "💰", "title": "...", "description": "..."}}
    ],
    "cta_primary": "Button text (örn: 'Book a Free Audit')",
    "cta_secondary": "Backup CTA (örn: 'See pricing')"
  }},
  "competitor_checklist": [
    "Her rakip için kontrol edilecek 8-10 spesifik bilgi. Örn: 'Fiyatlandırma modeli (aylık/yıllık/kullanım bazlı)', 'Hedef müşteri büyüklüğü (SMB/Enterprise)', 'Son 12 ayda yaptıkları duyuruları', ..."
  ],
  "known_competitors": ["3-5 somut rakip şirket ismi — aramadan önce kontrol edilecek isimler"],
  "success_metrics_30d": [
    "Ay sonunda hangi sayılar 'başarı'dır? Spesifik olsun. Örn: '10 müşteri görüşmesi tamamlandı', '1 pilot anlaşması imzalandı', 'Landing page 500 ziyaret + 20 email'"
  ],
  "fail_signals": [
    "Hangi sinyaller 'bırak bu fırsatı' demektir. Örn: '10 görüşmede 0 kişi bu problem için para ödemeye hazır değil'"
  ]
}}

KURALLAR:
- Vague ifadeler yerine ölçülebilir aksiyonlar (sayı, tarih, spesifik araç isimleri)
- Haftalar arası bağlantı olsun (hafta 1 öğrendiklerine göre hafta 2'yi şekillendir)
- Cold outreach gerçekten kişisel olsun — generic şablon değil
- Landing copy founder'ın gerçek avantajına atıfta bulunsun (Turkish manufacturing, UK entity, IT expertise vb)"""

    def _parse_kit(self, text: str) -> dict:
        """Parse JSON response with 3-strategy fallback."""
        text = text.strip()

        # Strategy 1: Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Code fence
        import re
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 3: First brace
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

        logger.error(f"Failed to parse action kit JSON: {text[:200]}")
        return {"_parse_error": True, "_raw": text[:2000]}

    def _save_to_kb(self, opp_id: str, kit: dict):
        """Save action kit to opportunities.action_kit_json column."""
        cursor = self.kb.conn.cursor()
        # Migration: add column if missing
        cursor.execute("PRAGMA table_info(opportunities)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'action_kit_json' not in columns:
            cursor.execute("ALTER TABLE opportunities ADD COLUMN action_kit_json TEXT")
            cursor.execute("ALTER TABLE opportunities ADD COLUMN action_kit_generated_at TEXT")

        cursor.execute("""
            UPDATE opportunities
            SET action_kit_json = ?,
                action_kit_generated_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = ?
        """, (json.dumps(kit, ensure_ascii=False), opp_id))
        self.kb.conn.commit()

    def format_as_markdown(self, opp: dict, kit: dict) -> str:
        """Format action kit as human-readable Markdown (for Telegram/email)."""
        lines = [
            f"# 🎬 Action Kit: {opp.get('title', '?')}",
            f"**ID:** `{opp.get('id', '?')}` · **Score:** {opp.get('weighted_total', 0):.0f}/155 · **Tier:** {opp.get('tier', '?')}",
            "",
            "## 📅 30-Day Plan",
        ]
        for week in kit.get('plan_30day', []):
            lines.append(f"\n**Week {week.get('week', '?')}: {week.get('theme', '')}**")
            for task in week.get('tasks', []):
                lines.append(f"- {task}")

        # Discovery questions
        if kit.get('discovery_questions'):
            lines.append("\n## 🎯 Customer Discovery Questions")
            for i, q in enumerate(kit['discovery_questions'], 1):
                lines.append(f"{i}. {q}")

        # Cold outreach
        co = kit.get('cold_outreach', {})
        if co:
            lines.append("\n## ✉️ Cold Outreach")
            lines.append(f"**Target:** {co.get('target_persona', '?')}")
            lines.append(f"**Channel:** {co.get('channel', '?')}")
            lines.append(f"**Subject:** {co.get('subject', '?')}")
            lines.append(f"\n```\n{co.get('body', '')}\n```")
            lines.append(f"\n**Follow-up:** {co.get('followup_cadence', '?')}")

        # Landing copy
        lc = kit.get('landing_copy', {})
        if lc:
            lines.append("\n## 🌐 Landing Page Copy")
            lines.append(f"### {lc.get('hero_headline', '?')}")
            lines.append(f"_{lc.get('subheadline', '')}_\n")
            for vp in lc.get('value_props', []):
                lines.append(f"- {vp.get('icon', '•')} **{vp.get('title', '?')}**: {vp.get('description', '')}")
            lines.append(f"\n**Primary CTA:** `{lc.get('cta_primary', '?')}`")
            lines.append(f"**Secondary CTA:** `{lc.get('cta_secondary', '?')}`")

        # Competitor checklist
        if kit.get('known_competitors'):
            lines.append("\n## 🏢 Known Competitors")
            for c in kit['known_competitors']:
                lines.append(f"- {c}")
        if kit.get('competitor_checklist'):
            lines.append("\n## ✅ Competitor Analysis Checklist")
            for item in kit['competitor_checklist']:
                lines.append(f"- [ ] {item}")

        # Success metrics
        if kit.get('success_metrics_30d'):
            lines.append("\n## 📊 30-Day Success Metrics")
            for m in kit['success_metrics_30d']:
                lines.append(f"- {m}")

        # Fail signals
        if kit.get('fail_signals'):
            lines.append("\n## 🛑 Fail Signals (kill-criteria)")
            for f in kit['fail_signals']:
                lines.append(f"- {f}")

        return "\n".join(lines)

    def format_as_html(self, opp: dict, kit: dict) -> str:
        """Format as HTML for email delivery."""
        md = self.format_as_markdown(opp, kit)
        # Simple markdown → HTML (keep it minimal)
        html = md.replace('\n', '<br>')
        # Convert # / ## headers
        import re
        html = re.sub(r'^###\s+(.+?)(<br>|$)', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^##\s+(.+?)(<br>|$)', r'<h2 style="color:#2c3e50;">\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^#\s+(.+?)(<br>|$)', r'<h1 style="color:#e74c3c;">\1</h1>', html, flags=re.MULTILINE)
        # Bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        # Italic
        html = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', html)
        # Inline code
        html = re.sub(r'`([^`]+)`', r'<code style="background:#f4f4f4;padding:2px 6px;border-radius:3px;">\1</code>', html)
        # Bullet lists
        html = re.sub(r'^- \[ \] (.+?)(<br>|$)', r'<li><input type="checkbox" disabled> \1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'^- (.+?)(<br>|$)', r'<li>\1</li>', html, flags=re.MULTILINE)

        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 700px; margin: 20px auto; padding: 20px; color: #333; line-height: 1.6; }}
  h1 {{ border-bottom: 3px solid #e74c3c; padding-bottom: 10px; }}
  h2 {{ margin-top: 30px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
  pre {{ background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; }}
  code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }}
  li {{ margin: 5px 0; }}
</style></head><body>
{html}
<hr style="margin-top:40px;"><small style="color:#999;">Generated by OpportunityScout Action Kit · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</small>
</body></html>"""
