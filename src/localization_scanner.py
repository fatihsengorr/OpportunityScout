"""
OpportunityScout — Localization Scanner v2 (5-Strategy Engine)

The "copy what works" module, now powered by 5 parallel search strategies:

  Strategy 1: MULTI-STAGE PIPELINE — Funded startups → gap check → adaptation
  Strategy 2: REVERSE SAMWER — UK pain points → global solutions → localization
  Strategy 3: ARBITRAGE SCANNER — UK vs Turkey price gaps → business models
  Strategy 4: FAILURE ANALYSIS — Failed UK startups → extract learnings → retry
  Strategy 5: CAPABILITY×MARKET MATRIX — 5 skills × trending sectors → gaps

All 5 run every cycle. Performance tracked per strategy.
Cost: ~$4-5 per cycle.
"""

import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from .llm_router import LLMRouter
from src.scoring_utils import calculate_weighted_total, determine_tier

logger = logging.getLogger("scout.localization")

FOUNDER_PROFILE_PATH = Path("./config/founder_profile.yaml")
SYSTEM_PROMPT_PATH = Path("./SYSTEM_PROMPT.md")


class LocalizationScanner:
    """
    5-Strategy Localization Engine.
    Finds proven models globally and evaluates localization potential.
    """

    STRATEGY_NAMES = [
        'multi_stage', 'reverse_samwer', 'arbitrage',
        'failure_analysis', 'capability_matrix'
    ]

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.llm = LLMRouter(config)
        self.model = self.llm.get_model('weekly')
        self._founder_profile = self._load_file(FOUNDER_PROFILE_PATH)
        self._system_prompt = self._load_file(SYSTEM_PROMPT_PATH)

    # ═══════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════

    def scan(self, focus_sector: str = None, count: int = 5) -> dict:
        """
        Run all 5 localization strategies and merge results.
        """
        logger.info(f"🌍 5-Strategy Localization scan starting"
                    f"{f' (focus: {focus_sector})' if focus_sector else ''}...")

        known_titles = self._get_known_titles()
        previous = self._get_previous_localizations()

        all_opportunities = []
        strategy_results = {}

        strategies = [
            ('multi_stage', self._strategy_multi_stage),
            ('reverse_samwer', self._strategy_reverse_samwer),
            ('arbitrage', self._strategy_arbitrage),
            ('failure_analysis', self._strategy_failure_analysis),
            ('capability_matrix', self._strategy_capability_matrix),
        ]

        for strategy_name, strategy_fn in strategies:
            start_time = time.time()
            logger.info(f"🌍 Running strategy: {strategy_name}")

            try:
                opps = strategy_fn(
                    known_titles=known_titles,
                    previous=previous,
                    focus_sector=focus_sector
                )

                duration = time.time() - start_time

                # Finalize and store
                stored = []
                for opp in opps:
                    opp['_strategy'] = strategy_name
                    opp = self._finalize_opportunity(opp)
                    if not self.kb.is_duplicate(
                        opp.get('title', ''), 'localization_scanner',
                        sector=opp.get('sector'), tags=opp.get('tags', [])
                    ):
                        self.kb.save_opportunity(opp)
                        stored.append(opp)

                # Track performance
                fire_count = len([o for o in stored if o.get('tier') == 'FIRE'])
                high_count = len([o for o in stored if o.get('tier') == 'HIGH'])
                scores = [o.get('weighted_total', 0) for o in stored]

                self.kb.log_strategy_performance(
                    engine='localization',
                    strategy_name=strategy_name,
                    opportunities_found=len(stored),
                    avg_score=round(sum(scores) / len(scores), 1) if scores else 0,
                    best_score=max(scores) if scores else 0,
                    fire_count=fire_count,
                    high_count=high_count,
                    duration_seconds=round(duration, 1)
                )

                strategy_results[strategy_name] = {
                    'raw': len(opps),
                    'stored': len(stored),
                    'fire': fire_count,
                    'high': high_count,
                    'best': max(scores) if scores else 0,
                    'avg': round(sum(scores) / len(scores), 1) if scores else 0,
                    'duration': round(duration, 1)
                }

                all_opportunities.extend(stored)
                known_titles.extend([o.get('title', '') for o in stored])

                logger.info(
                    f"🌍 {strategy_name}: {len(opps)} raw → {len(stored)} stored "
                    f"(🔥{fire_count} ⭐{high_count}) in {duration:.0f}s"
                )

            except Exception as e:
                logger.error(f"🌍 Strategy {strategy_name} failed: {e}")
                strategy_results[strategy_name] = {'error': str(e)}

        # Summary
        total = len(all_opportunities)
        logger.info(f"{'='*50}")
        logger.info(f"🌍 5-STRATEGY LOCALIZATION COMPLETE")
        logger.info(f"   Total: {total} opportunities")
        for name, r in strategy_results.items():
            if isinstance(r, dict) and 'error' not in r:
                logger.info(f"   {name}: {r['stored']} opps, best={r['best']}")
        logger.info(f"{'='*50}")

        return {
            "mode": "localization_5strategy",
            "focus_sector": focus_sector,
            "models_analyzed": sum(r.get('raw', 0) for r in strategy_results.values() if isinstance(r, dict)),
            "opportunities_stored": total,
            "opportunities": all_opportunities,
            "strategy_results": strategy_results,
            "timestamp": datetime.utcnow().isoformat()
        }

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 1: MULTI-STAGE PIPELINE
    # ═══════════════════════════════════════════════════════════

    def _strategy_multi_stage(self, **kwargs) -> list:
        """Kademeli Startup Araştırması — structured funded model discovery."""
        focus = kwargs.get('focus_sector', '')
        focus_text = f"\nFocus on: {focus}" if focus else ""

        prompt = f"""Sen OpportunityScout'un Multi-Stage Pipeline stratejisisin.

GÖREVİN: Fonlanmış, büyüyen startup'ları sistematik olarak bul, UK/TR boşluğunu kontrol et.
{focus_text}

ADIM A — KEŞFET: 2025-2026'da en hızlı büyüyen B2B kategorileri neler?
Web'de ara: "fastest growing B2B startups 2025", "YC batch 2025 top companies", "Series A funding 2025 2026"
En az 5 farklı kategori bul.

ADIM B — ŞİRKETLERİ BUL: Her kategori için top 3-5 şirket:
- Şirket adı, ülke, ne yapar, funding, revenue sinyalleri

ADIM C — BOŞLUK KONTROLÜ: Her şirket için:
- "[company] UK competitor alternative" ara
- "[company's service] Turkey" ara
- UK'de var mı? TR'de var mı? Kalite nasıl?

ADIM D — ADAPTASYON: Boşluk olan şirketler için founder fit + adaptasyon planı.

OPERATOR PROFILE:
{self._founder_profile}

BİLİNEN BAŞLIKLAR (tekrarlama):
{chr(10).join(f'- {t}' for t in kwargs.get('known_titles', [])[:15])}

{self._get_localization_json_template()}

En az 8 web araması yap. Sadece GERÇEK, doğrulanabilir şirketler."""

        return self._execute_and_parse(prompt)

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 2: REVERSE SAMWER (Problem-First)
    # ═══════════════════════════════════════════════════════════

    def _strategy_reverse_samwer(self, **kwargs) -> list:
        """UK pain points → who solved it elsewhere → localize."""
        prompt = f"""Sen OpportunityScout'un Reverse Samwer stratejisisin.

GÖREVİN: UK SME'lerin en büyük acı noktalarını bul, başka ülkelerde kim çözmüş bak.

ADIM A — ACI NOKTALARI: Web'de ara:
- "UK small business biggest challenges 2025"
- "UK SME most expensive services"
- "what UK businesses complain about most"
- Reddit UK business forums, Trustpilot complaints
En az 10 farklı acı noktası bul.

ADIM B — GLOBAL ÇÖZÜMLER: Her acı noktası için:
- "best [problem] solution startup"
- "[problem] solved India startup"
- "[problem] solved US company"
Kim çözmüş? Nasıl? Ne kadar fiyat alıyor?

ADIM C — LOKALİZASYON: UK'ye getirebilir miyiz?
- Turkish cost + UK price ile adapte edilebilir mi?
- Founder'ın yetenekleriyle eşleşiyor mu?

OPERATOR PROFILE:
{self._founder_profile}

BİLİNEN BAŞLIKLAR (tekrarlama):
{chr(10).join(f'- {t}' for t in kwargs.get('known_titles', [])[:15])}

{self._get_localization_json_template()}

En az 8 web araması yap. Gerçek acı noktaları, gerçek çözümler."""

        return self._execute_and_parse(prompt)

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 3: ARBITRAGE SCANNER (Price-Gap)
    # ═══════════════════════════════════════════════════════════

    def _strategy_arbitrage(self, **kwargs) -> list:
        """Mathematical price-gap analysis between UK and Turkey."""
        prompt = f"""Sen OpportunityScout'un Arbitrage Scanner stratejisisin.

GÖREVİN: UK fiyatı ile Turkey maliyeti arasındaki en büyük spread'leri bul.

ADIM A — FİYAT ARAŞTIRMASI: Web'de şunları ara:
- "average cost [service] UK per hour" (IT support, design, development, consulting, accounting, etc.)
- "freelancer rates Turkey [service]"
- "outsourcing costs Turkey vs UK"
- Manufacturing costs Turkey vs UK for specific products

EN AZ 15 B2B hizmet/ürün kategorisinin UK fiyatını ve Turkey maliyetini bul:
1. IT managed services
2. Software development
3. Cybersecurity services
4. Graphic design / branding
5. Accounting / bookkeeping
6. Legal document preparation
7. Customer service / call center
8. CNC machining / manufacturing
9. Furniture production
10. Industrial coatings / painting
11. Data entry / processing
12. Content creation / copywriting
13. 3D modeling / BIM services
14. Quality inspection
15. Packaging and logistics

ADIM B — SPREAD HESAPLA: UK price / Turkey cost = margin multiplier
En büyük spread'leri sırala.

ADIM C — İŞ MODELİ: Top 3-5 spread için:
- Bu spread'i exploit edecek spesifik iş modeli ne?
- Founder hangi yeteneklerini kullanır?
- Kalite nasıl garanti edilir?
- Customer acquisition nasıl?

OPERATOR PROFILE:
{self._founder_profile}

{self._get_localization_json_template()}

Matematiksel ol. Gerçek fiyat verileri bul."""

        return self._execute_and_parse(prompt)

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 4: FAILURE ANALYSIS
    # ═══════════════════════════════════════════════════════════

    def _strategy_failure_analysis(self, **kwargs) -> list:
        """Learn from UK startup failures — validated demand, known pitfalls."""
        prompt = f"""Sen OpportunityScout'un Failure Analysis stratejisisin.

GÖREVİN: UK'de başarısız olan startup'ları bul, neden başarısız olduklarını anla, founder bu tuzaklardan kaçınabilir mi değerlendir.

ADIM A — BAŞARISIZ STARTUP'LAR: Web'de ara:
- "UK startups that failed 2023 2024 2025"
- "UK startup post-mortems"
- "companies that shut down UK 2024"
- "startup failures lessons learned UK"
- "UK tech companies that pivoted or closed"

En az 10 başarısız/kapanan/pivot eden UK startup bul.

ADIM B — ANALİZ: Her biri için:
- Ne yapıyordu?
- Neden başarısız? (Timing? Capital? Execution? Market? Team?)
- Demand var mıydı? (customers were they growing?)
- Ne kadar fonlanmıştı?

ADIM C — FOUNDER FİLTRESİ: Başarısızlık nedeni founder için geçerli mi?
- "Too expensive to build" → Founder has Turkish cost advantage → MAYBE
- "Couldn't find product-market fit" → Demand was never there → SKIP
- "Ran out of capital" → Founder can bootstrap with AI → MAYBE
- "Poor execution" → Founder has domain expertise → MAYBE
- "Bad timing" → Timing better now? → CHECK

ADIM D — YENİDEN TASARLA: Geçerli olmayan başarısızlık nedenleri olan startup'lar için:
- Aynı problemi founder nasıl çözer?
- AI ile nasıl daha ucuza yapılır?
- Cross-border avantajı nasıl kullanılır?

OPERATOR PROFILE:
{self._founder_profile}

{self._get_localization_json_template()}

En az 6 web araması yap. Gerçek kapanmış/başarısız şirketler."""

        return self._execute_and_parse(prompt)

    # ═══════════════════════════════════════════════════════════
    # STRATEGY 5: CAPABILITY×MARKET MATRIX
    # ═══════════════════════════════════════════════════════════

    def _strategy_capability_matrix(self, **kwargs) -> list:
        """5 capability clusters × trending sectors → find empty cells."""
        prompt = f"""Sen OpportunityScout'un Capability×Market Matrix stratejisisin.

GÖREVİN: Founder'ın 5 yetenek cluster'ını trending sektörlerle çaprazla, boş hücreleri bul.

ADIM A — TREND SEKTÖRLER: Web'de ara:
- "fastest growing industries 2025 2026"
- "emerging markets UK business opportunities"
- "trending B2B sectors"
Top 8-10 trending sektör bul.

ADIM B — MATRİS OLUŞTUR:
5 Yetenek × 10 Sektör = 50 hücre

Yetenekler:
1. Fabrika (CNC, coil coating, üretim)
2. IT Altyapı (Cisco, VMware, Palo Alto, VDI)
3. AI/Yazılım (Python, n8n, Claude API, AWS)
4. Cross-border (UK-TR-UAE-US şirketler)
5. İnşaat (BSA, yangın kapılar, BIM)

Her hücre için: "Bu kesişimde dünyada proven bir model var mı?"
Hızlıca web'de ara: "[capability] [sector] startup company"

ADIM C — BOŞ HÜCRELER:
Hiç kimsenin bakmadığı hücreler = en büyük fırsat
Özellikle IT Altyapı ve Cross-border satırlarındaki boş hücreler çok değerli.

ADIM D — İŞ MODELİ: Top 2-3 boş hücre için spesifik iş modeli tasarla.

OPERATOR PROFILE:
{self._founder_profile}

{self._get_localization_json_template()}

Sistematik ol. Her hücreyi kısaca değerlendir, en iyi boşluklar için detaylı model yaz."""

        return self._execute_and_parse(prompt)

    # ═══════════════════════════════════════════════════════════
    # SHARED EXECUTION
    # ═══════════════════════════════════════════════════════════

    def _execute_and_parse(self, prompt: str) -> list:
        """Execute a multi-turn web search and parse localization results."""
        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.llm.create(
                model=self.model,
                max_tokens=8192,
                system=self._system_prompt,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=messages
            )

            loop_count = 0
            while response.stop_reason == "tool_use" and loop_count < 25:
                loop_count += 1
                logger.info(f"   🌍 Search loop {loop_count}")
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Search completed."
                        })

                messages.append({"role": "user", "content": tool_results})
                response = self.llm.create(
                    model=self.model,
                    max_tokens=8192,
                    system=self._system_prompt,
                    tools=[{"type": "web_search_20250305", "name": "web_search"}],
                    messages=messages
                )

            text = self._extract_text(response)
            results = self._parse_response(text)
            return results.get('opportunities', [])

        except Exception as e:
            logger.error(f"Localization search failed: {e}")
            return []

    def _get_localization_json_template(self) -> str:
        """Shared JSON output format for all strategies."""
        return """Include "action_by" date (YYYY-MM-DD or null) for time-sensitive opportunities.

Sonuçları şu JSON formatında döndür:
```json
{
  "opportunities": [
    {
      "title": "Localized model name",
      "one_liner": "Tek cümle açıklama",
      "original_model": {
        "company": "Orijinal şirket",
        "country": "Ülke",
        "funding": "Funding",
        "what_they_do": "Ne yapıyor",
        "url": "Website"
      },
      "gap_analysis": {
        "uk_status": "NO_EQUIVALENT | WEAK_EQUIVALENT",
        "uk_competitors": "Varsa UK rakipler",
        "turkey_status": "NO_EQUIVALENT | WEAK_EQUIVALENT",
        "turkey_competitors": "Varsa TR rakipler",
        "why_gap_exists": "Neden boşluk var?"
      },
      "localization_plan": {
        "target_market": "UK | Turkey | Both",
        "key_adaptations": "Ne değişmeli",
        "ai_acceleration": "AI nasıl ucuzlatır",
        "cross_border_angle": "UK↔TR avantajı"
      },
      "business_model": {
        "revenue_type": "SaaS|Marketplace|Service|Product",
        "pricing": "Spesifik fiyatlandırma",
        "time_to_revenue": "Ne zaman gelir"
      },
      "founder_edge": "Neden BU founder?",
      "first_move": "İlk 48 saatte ne yapılacak",
      "kill_criteria": "Neyi görürsen vazgeç",
      "confidence": "HIGH|MEDIUM|LOW",
      "sector": "Sektör",
      "geography": "UK|Turkey|Both",
      "tags": ["localization", "samwer-model", "tag"],
      "scores": {
        "founder_fit": {"score": 8, "reason": "..."},
        "ai_unlock": {"score": 7, "reason": "..."},
        "time_to_revenue": {"score": 8, "reason": "..."},
        "capital_efficiency": {"score": 9, "reason": "..."},
        "market_timing": {"score": 7, "reason": "..."},
        "defensibility": {"score": 6, "reason": "..."},
        "scale_potential": {"score": 7, "reason": "..."},
        "geographic_leverage": {"score": 9, "reason": "..."},
        "competition_gap": {"score": 9, "reason": "..."},
        "simplicity": {"score": 7, "reason": "..."}
      }
    }
  ]
}
```"""

    # ═══════════════════════════════════════════════════════════
    # RESULT PROCESSING
    # ═══════════════════════════════════════════════════════════

    def _finalize_opportunity(self, opp: dict) -> dict:
        """Calculate score and finalize for storage."""
        scores = opp.get('scores', {})
        opp['weighted_total'] = self._calculate_weighted_total(scores)
        opp['tier'] = self._determine_tier(opp['weighted_total'])
        opp['source'] = 'localization_scanner'

        if 'localization' not in opp.get('tags', []):
            opp.setdefault('tags', []).append('localization')
        if 'samwer-model' not in opp.get('tags', []):
            opp.setdefault('tags', []).append('samwer-model')

        opp.setdefault('why_now', opp.get('gap_analysis', {}).get('why_gap_exists', ''))
        opp.setdefault('first_move', opp.get('first_move', ''))
        opp.setdefault('revenue_path', opp.get('business_model', {}).get('pricing', ''))
        opp.setdefault('risks', [opp.get('kill_criteria', 'Unknown')])
        opp.setdefault('sector', opp.get('sector', ''))
        opp.setdefault('geography', opp.get('geography', 'UK'))
        opp['source_date'] = datetime.utcnow().strftime('%Y-%m-%d')

        # ID is assigned by knowledge_base.save_opportunity() — no need to set here

        return opp

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _get_known_titles(self) -> list:
        opps = self.kb.get_top_opportunities(limit=30)
        return [o.get('title', '') for o in opps if o.get('title')]

    def _get_previous_localizations(self) -> list:
        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT title FROM opportunities
                WHERE source = 'localization_scanner'
                ORDER BY created_at DESC LIMIT 20
            """)
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    def _calculate_weighted_total(self, scores: dict) -> float:
        return calculate_weighted_total(scores, self.config)

    def _determine_tier(self, weighted_total: float) -> str:
        return determine_tier(weighted_total, self.config)

    def _parse_response(self, text: str) -> dict:
        """Extract JSON with multiple fallback strategies including truncation repair."""
        import re
        default = {"opportunities": []}

        if not text or not text.strip():
            return default

        # Strategy 1: Direct parse
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Strategy 2: Code fence
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find first '{' and parse from there
        first_brace = text.find('{')
        if first_brace >= 0:
            json_candidate = text[first_brace:]
            try:
                return json.loads(json_candidate)
            except json.JSONDecodeError:
                pass

            # Strategy 4: Repair truncated JSON
            repaired = self._repair_truncated_json(json_candidate)
            if repaired:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass

        logger.warning("Could not parse JSON from localization response")
        logger.warning(f"Raw text (first 500): {text[:500]}")
        return default

    @staticmethod
    def _repair_truncated_json(text: str) -> str:
        """Repair truncated JSON by closing open brackets/braces."""
        if not text:
            return ""
        depth_brace = 0
        depth_bracket = 0
        last_safe_pos = 0
        in_string = False
        escape_next = False

        for i, ch in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth_brace += 1
            elif ch == '}':
                depth_brace -= 1
                if depth_brace >= 0:
                    last_safe_pos = i + 1
            elif ch == '[':
                depth_bracket += 1
            elif ch == ']':
                depth_bracket -= 1

        if depth_brace == 0 and depth_bracket == 0:
            return text

        repaired = text[:last_safe_pos]
        depth_brace = 0
        depth_bracket = 0
        in_string = False
        escape_next = False
        for ch in repaired:
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth_brace += 1
            elif ch == '}':
                depth_brace -= 1
            elif ch == '[':
                depth_bracket += 1
            elif ch == ']':
                depth_bracket -= 1

        repaired += ']' * depth_bracket + '}' * depth_brace
        return repaired

    @staticmethod
    def _extract_text(response) -> str:
        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text
        return text

    @staticmethod
    def _load_file(path: Path) -> str:
        try:
            return path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return ""
