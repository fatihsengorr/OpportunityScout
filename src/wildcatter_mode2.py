"""
Wildcatter Mod 2 — Unicorn Avı (Sektörsüz)

Fatih's own words: "Ben girişimciyim, sektör adamı değilim. Yemeksepeti de yaparım,
bunu da yaparım."

Mod 2 is the counter-balance to Mod 1 (ThreadForge feed). Where Mod 1 is disciplined
and narrow, Mod 2 is broad and sector-agnostic. It hunts for unicorn-scale opportunities
that would make Fatih say "vay" — 3-5 per year, never a blank year.

Mechanics:
  - Filters: only opportunities passing wow_threshold
  - Prompt context: deliberately excludes construction, challenges "obvious" sectors
  - Sources: prefers Family 1 (science/patent), Family 2 (infrastructure), Family 5 (cost curves)
  - Excludes: Mod 1 ThreadForge-tagged findings

Output: Opportunities saved to DB with mode='mod2_unicorn' tag. VAY tier fires
🌟 alert. Contributes to 4-layer output (Tomografi, Theses, Candidates, Alarms).
"""

import json
import logging
from datetime import datetime
from .llm_router import LLMRouter

logger = logging.getLogger("scout.mode2")


class WildcatterMode2:
    """Sector-agnostic unicorn hunting, filtered via Pattern + Wow."""

    def __init__(self, config: dict, knowledge_base, pattern_matcher=None,
                 wow_threshold=None):
        self.config = config
        self.kb = knowledge_base
        self.patterns = pattern_matcher
        self.wow = wow_threshold
        self.llm = LLMRouter(config)
        # Mod 2 uses weekly model (Claude Sonnet) — deep reasoning for unicorn-level
        self.model = self.llm.get_model('weekly')

    # ─── Public API ────────────────────────────────────────

    def run(self, num_searches: int = 3) -> dict:
        """Execute Mod 2 search — returns candidates passing Pattern + Wow filter.

        num_searches: How many different unicorn-hunt prompts to execute
        (each is an independent angle).
        """
        logger.info(f"🦄 Mod 2 Unicorn Avı: {num_searches} arama başlıyor")

        candidates = []
        for i in range(num_searches):
            try:
                result = self._unicorn_search(search_index=i, total=num_searches)
                candidates.extend(result.get('opportunities', []))
            except Exception as e:
                logger.error(f"Mod 2 search {i+1} failed: {e}")

        logger.info(f"🦄 Raw candidates: {len(candidates)}")

        # Filter: only candidates passing basic sanity (not construction-heavy, has score)
        filtered = []
        for cand in candidates:
            # Auto-reject if primarily construction/BTR/BSA-themed
            sector = (cand.get('sector') or '').lower()
            if any(kw in sector for kw in ['construction', 'btr', 'fit-out',
                                            'building safety', 'fire door']):
                logger.info(f"🦄 Rejecting {cand.get('title', '?')[:50]} — construction domain")
                continue
            filtered.append(cand)

        logger.info(f"🦄 After construction filter: {len(filtered)}")

        # Enrich with Pattern + Wow evaluation for each
        evaluated = []
        for cand in filtered:
            try:
                # Save to DB first so we have an ID
                opp_id = self.kb.save_opportunity(cand)
                cand['id'] = opp_id
                cand['mode'] = 'mod2_unicorn'

                # Pattern match
                if self.patterns:
                    pattern_result = self.patterns.match_and_save(opp_id, cand)
                    cand['_pattern_result'] = pattern_result
                    # Refresh from DB to get latest state
                    cursor = self.kb.conn.cursor()
                    cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
                    cand.update(dict(cursor.fetchone()))

                # Wow threshold only if patterns high-match or wow_candidate
                if (self.wow and
                    cand.get('pattern_count', 0) >= 3 and
                    cand.get('tier') == 'FIRE'):
                    wow_result = self.wow.evaluate_and_save(opp_id, cand)
                    cand['_wow_result'] = wow_result
                    if wow_result.get('verdict') == 'VAY':
                        cand['is_vay'] = True

                evaluated.append(cand)
            except Exception as e:
                logger.warning(f"Could not enrich {cand.get('title', '?')[:30]}: {e}")

        vay_count = sum(1 for c in evaluated if c.get('is_vay'))
        logger.info(f"🦄 Mod 2 complete: {len(evaluated)} opportunities, {vay_count} VAY")

        return {
            'mode': 'mod2_unicorn',
            'candidates_raw': len(candidates),
            'candidates_filtered': len(filtered),
            'candidates_evaluated': len(evaluated),
            'vay_count': vay_count,
            'opportunities': evaluated,
            'generated_at': datetime.utcnow().isoformat(),
        }

    # ─── Unicorn search ────────────────────────────────────

    def _unicorn_search(self, search_index: int, total: int) -> dict:
        """Execute one sector-agnostic unicorn-hunt prompt."""

        # 3 different angles for variety — each prompt asks a different question
        angles = [
            self._prompt_cost_curve_angle(),
            self._prompt_primitive_launch_angle(),
            self._prompt_cross_border_arbitrage_angle(),
        ]
        prompt = angles[search_index % len(angles)]

        logger.info(f"🦄 Unicorn search {search_index+1}/{total}: angle "
                    f"{['cost_curve', 'primitive', 'arbitrage'][search_index % 3]}")

        response = self.llm.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
        )

        # Multi-turn web search loop (Claude only — Gemini single-pass)
        messages = [{"role": "user", "content": prompt}]
        loop_count = 0
        max_loops = 15
        while response.stop_reason == "tool_use" and loop_count < max_loops:
            loop_count += 1
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if getattr(block, 'type', None) == "tool_use":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Search completed."
                    })
            messages.append({"role": "user", "content": tool_results})
            response = self.llm.create(
                model=self.model,
                max_tokens=4096,
                messages=messages,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
            )

        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text

        parsed = self._parse_json(text)
        if not parsed or 'opportunities' not in parsed:
            return {'opportunities': []}
        return parsed

    def _base_prompt_header(self) -> str:
        """Shared context — anti-construction bias."""
        return """Sen Wildcatter Mod 2'sin — Fatih için sektörsüz unicorn avı yapıyorsun.

FATİH'İN KİMLİĞİ: Girişimci, sektör adamı DEĞİL. "Yemeksepeti de yaparım, bunu da yaparım."
47 yaşında, TR/UK/UAE/US entities, 20.000 m² fabrika, AI fluency, concordato süreci aktif.

KESİN KURAL: **İnşaat, BTR, fire door, BSA, construction sektörlerini YAZMA.**
ThreadForge bunları zaten kapsıyor. Mod 2 tamamen farklı alanlara bakar:
biotech, fintech, AI infrastructure, cross-border arbitraj, materials science,
consumer products, developer tools, compliance-tech (non-construction).

HEDEF: Yılda 3-5 "vay" fırsatı — yeterince büyük ki Fatih "yaparım" desin.
Gallagher/Medvi tipi (AI × DTC × sağlık × kontrol) fırsatlar arıyoruz.
"""

    def _prompt_cost_curve_angle(self) -> str:
        """Prompt: hangi maliyet eğrisi kırıldı, ne açıyor?"""
        return self._base_prompt_header() + """
ANGLE: MALİYET EĞRİSİ KIRILMASI

Web'de ara:
1. Son 6 ayda %20+ düşen API/donanım/sensör/lojistik fiyatı
2. Anthropic/OpenAI/Google AI yeni fiyat düşüşleri 2026
3. GPU/RAM/sensör fiyat trendleri (NVIDIA, IoT donanım)
4. Drewry Container Index cross-border arbitraj penceresi
5. Energy/commodity maliyet kırılmaları (çelik, alüminyum, bakır, lityum)

Her düşüş için sor: "Bu maliyet eğrisi kırıldığı için geçen yıl ekonomik olmayan,
bu yıl ekonomik olan iş modeli nedir? Hangi unicorn bu kırılmadan doğar?"

HEDEF: Fatih'in 47 yaşında 2 çocuklu Londra taşınma bağlamında taşınabilir,
platform yapılı, 3+ yan iş kapısı açan fırsatlar.

SADECE JSON:
{
  "opportunities": [
    {
      "title": "...",
      "one_liner": "...",
      "sector": "non-construction sector",
      "why_now": "Hangi maliyet eğrisi kırıldı",
      "first_move": "İlk 48 saatte yapılacak somut aksiyon",
      "revenue_path": "90 gün içinde gelir yolu",
      "risks": ["...", "..."],
      "scores": {
        "founder_fit": {"score": 8, "reason": "..."},
        "ai_unlock": {"score": 9, "reason": "..."},
        "time_to_revenue": {"score": 7, "reason": "..."},
        "capital_efficiency": {"score": 8, "reason": "..."},
        "market_timing": {"score": 9, "reason": "..."},
        "defensibility": {"score": 7, "reason": "..."},
        "scale_potential": {"score": 9, "reason": "..."},
        "geographic_leverage": {"score": 8, "reason": "..."},
        "competition_gap": {"score": 7, "reason": "..."},
        "simplicity": {"score": 6, "reason": "..."}
      },
      "tags": ["cost-curve", "infrastructure", ...]
    }
  ]
}

En az 5 arama yap. 1-3 gerçekten unicorn-potansiyelli fırsat döndür."""

    def _prompt_primitive_launch_angle(self) -> str:
        """Prompt: hangi yeni B2B primitive açıldı, üzerine ne kurulur?"""
        return self._base_prompt_header() + """
ANGLE: YENİ B2B PRIMITIVE LANSMANI

Web'de ara:
1. Stripe son 6 ayda hangi yeni feature duyurdu
2. Anthropic/OpenAI changelog son 3 ay: geçen ay yapılamayan bu ay yapılabilen
3. Cloudflare Workers, Vercel, Supabase yeni primitive'ler
4. HuggingFace Daily Papers viral tekniği
5. AI Agent framework lansmanları (AutoGPT, CrewAI, BabyAGI ilerlemeleri)

Her primitive için sor: "Bu yeni primitive üzerine 6-12 ay içinde kurulacak
unicorn-ölçek iş nedir?"

Fatih'in altyapı avantajı: TR fabrika (üretim wrapper'ı olabilir),
AI fluency (primitive'i mikrofayda'ya çevirebilir), cross-border entities.

SADECE JSON (aynı format üstteki gibi). 1-3 fırsat döndür."""

    def _prompt_cross_border_arbitrage_angle(self) -> str:
        """Prompt: hangi ülkede var, diğerinde yok — arbitraj fırsatı?"""
        return self._base_prompt_header() + """
ANGLE: CROSS-BORDER ARBİTRAJ (non-construction)

Web'de ara:
1. US/Asya'da patlayan DTC markalar TR üretim kapasitesiyle yerleştirilebilir mi
2. TR'de yapılabilen, UK/EU'de premium fiyatla satılan sektörler (saatlik rate arbitrajı)
3. Düzenleyici arbitraj — bir ülkede yasak, diğerinde legal hizmetler
4. Gallagher/Medvi tipi: verifiable, DTC, AI-driven sektörler (sağlık, longevity, mental health)
5. Şikayetvar/Trustpilot toplu şikayet temaları — global çözümü TR üretimle

Fatih'in UK/TR/UAE/US entity kombinasyonu + fabrika + AI knowhow.
Fırsat yapısal olarak "TR maliyet × UK/US fiyat × AI ölçek" olmalı.

SADECE JSON (aynı format). 1-3 fırsat döndür."""

    # ─── Parsing ──────────────────────────────────────────

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
