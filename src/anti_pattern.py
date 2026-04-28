"""
OpportunityScout — Anti-Echo Chamber

İki fonksiyon:
  1. is_concept_duplicate(opp, kb, llm) — Aşama 1: kavram-seviyesi dedup
     Yeni fırsat kaydedilmeden önce, son N günde benzer kavram üretildi mi
     diye Gemini Flash ile kontrol et. "TR-UK arbitrage in furniture" ile
     "TR-UK arbitrage in chemicals" — aynı kavram. is_duplicate (title-only)
     bunları yakalayamaz, bu fonksiyon yakalar.

  2. get_anti_pattern_block(kb, days) — Aşama 2: prompt'a enjekte edilecek
     "ZATEN DOYMUŞ KAVRAMLAR" bloku. Her discovery motor scan başlangıcında
     bu bloku çağırır, prompt'a eklenir. Generation aşamasında "tekrar
     etme" sinyali → API harcaması azalır.

Kullanıcının ifadesi (28 Nisan 2026):
  "Mavi, açık mavi, parlement mavi gibi aynı şeyleri görüyorum hep.
   Bunlar artık fırsat değil, sadece tekrar."
"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger("scout.anti_pattern")


# ─── Aşama 2: Anti-Pattern Block Builder ──────────────────────────────

# Takip edilecek kavram kalıpları (regex desteği var)
CONCEPT_PATTERNS = [
    ("TR-UK cross-border arbitrage", [
        r"cross[- ]border", r"tr[- ]uk", r"turkey[- ]uk", r"uk[- ]turkey",
        r"uk[- ]tr", r"türkiye[- ]uk",
    ]),
    ("Turkish manufacturing + UK market", [
        r"turkish manufactur", r"tr factory", r"turkey factory",
        r"turkish cnc", r"türk üretim", r"türkiye fabrika",
    ]),
    ("Building Safety Act / Golden Thread", [
        r"building safety", r"golden thread", r"\bbsa\b", r"gateway 3",
    ]),
    ("Fire door / Fire safety", [
        r"fire door", r"fire safety", r"intumescent",
    ]),
    ("BIM / Scan-to-BIM", [
        r"\bbim\b", r"scan[- ]to[- ]bim", r"digital twin", r"point cloud",
    ]),
    ("Coil coating / specialty paint", [
        r"coil coating", r"coil paint", r"specialty coating",
        r"specialty paint",
    ]),
    ("AI compliance automation", [
        r"ai[- ]powered compliance", r"ai compliance",
        r"compliance automation", r"automated compliance",
    ]),
    ("BTR furniture", [
        r"\bbtr\b", r"build[- ]to[- ]rent",
    ]),
    ("Cross-border arbitrage (generic)", [
        r"arbitrage hub", r"arbitrage platform", r"arbitrage service",
    ]),
    ("AI chatbot / customer service", [
        r"ai chatbot", r"customer service.*ai", r"ai customer",
    ]),
    ("Manufacturing SaaS (UK SME wrapper)", [
        r"manufacturing.*saas", r"saas.*manufacturing", r"uk sme",
    ]),
]


def get_anti_pattern_block(kb, days: int = 30, min_count: int = 3) -> str:
    """Build dynamic 'don't repeat' block for prompt injection.

    Queries last N days of opps from KB, counts saturation per concept
    pattern, returns markdown block listing saturated patterns + new
    angle suggestions. Empty string if nothing saturated.
    """
    cursor = kb.conn.cursor()
    cursor.execute("""
        SELECT title, sector, tags_json
        FROM opportunities
        WHERE created_at >= datetime('now', '-' || ? || ' days')
    """, (days,))
    rows = list(cursor.fetchall())

    if not rows:
        return ""

    counts = {}
    examples = {}
    for row in rows:
        title = (row['title'] or '').lower()
        sector = (row['sector'] or '').lower()
        tags = (row['tags_json'] or '').lower()
        text = f"{title} {sector} {tags}"

        for concept_name, keywords in CONCEPT_PATTERNS:
            for kw in keywords:
                if re.search(kw, text):
                    counts[concept_name] = counts.get(concept_name, 0) + 1
                    if concept_name not in examples:
                        examples[concept_name] = row['title'][:60]
                    break  # only count once per opp per concept

    saturated = [
        (name, cnt, examples.get(name, ''))
        for name, cnt in counts.items()
        if cnt >= min_count
    ]
    saturated.sort(key=lambda x: -x[1])

    if not saturated:
        return ""

    block = f"\n🚫 ZATEN DOYMUŞ KAVRAMLAR — TEKRAR ÜRETME (son {days} gün):\n"
    for name, cnt, example in saturated[:8]:
        block += f"  - '{name}' kalıbı **{cnt} varyantta** üretildi (örn: \"{example}\")\n"

    block += (
        "\n"
        "**KRİTİK:** Bu kavramların FARKLI bir sektör paketleyişini üretme.\n"
        "Aynı 'TR-UK arbitrage' template'i — sadece sektör değiştirmek = TEKRAR.\n"
        "TAMAMEN YENİ angle bul:\n"
        "  - Cross-border DEĞİL: tek-ülke / pure-UK / pure-TR / pure-US / pure-EU fırsat\n"
        "  - Manufacturing wrapper DEĞİL: software-only / API/data play / consumer DTC / marketplace dynamics\n"
        "  - Compliance wrapper DEĞİL: tech disruption (gen-AI breakthroughs, sensor cost crash, materials science)\n"
        "  - Sector arbitrage DEĞİL: business model arbitrage (vertical SaaS, demand aggregation, regulatory window — non-construction)\n"
        "  - 'Fatih'in kombinasyonu' DEĞİL: Pattern #7 (Taahhüt-Önce) tek başına yeterli — yeni öğrenme alanı kabul\n"
        "\n"
        "Eğer tüm yeni angle'ların yine yukarıdaki doymuş kalıplara mecburi düşüyorsa,\n"
        "BU FIRSATI ÜRETME — boş çıktı 'tekrar' çıktısından iyidir.\n"
    )

    return block


# ─── Aşama 1: Semantic Concept Duplicate Check ─────────────────────────

def is_concept_duplicate(opp: dict, kb, llm_router,
                         days: int = 60,
                         min_jaccard: float = 0.20,
                         max_candidates: int = 8) -> dict:
    """Check if opp is a concept-level duplicate of recent ones.

    Two-stage filter:
      1. Quick rule-based: word-level Jaccard ≥ min_jaccard with existing opps
      2. LLM check on top candidates (only if stage 1 finds matches)

    Returns:
      {
        'is_echo': bool,
        'similar_count': int,
        'similar': [{title, id, ...}, ...],
        'concept_signature': str (kavram özeti),
        'reason': str,
        'recommendation': 'reject' | 'downgrade' | 'flag' | 'accept'
      }

    Recommendation logic:
      - similar ≥4 → 'reject' (drop entirely)
      - similar 2-3 → 'downgrade' (FIRE→HIGH, HIGH→MEDIUM)
      - similar 1 → 'flag' (kayıt et ama not düş)
      - similar 0 → 'accept'
    """
    cursor = kb.conn.cursor()
    cursor.execute("""
        SELECT id, title, one_liner, sector, weighted_total
        FROM opportunities
        WHERE created_at >= datetime('now', '-' || ? || ' days')
        ORDER BY weighted_total DESC
        LIMIT 50
    """, (days,))
    recent = [dict(r) for r in cursor.fetchall()]

    if len(recent) < 2:
        return _accept_result()

    # Rule-based pre-filter — significant word Jaccard
    new_text = ((opp.get('title') or '') + ' ' +
                (opp.get('one_liner') or '')).lower()
    new_words = set(w for w in re.findall(r'\b\w+\b', new_text) if len(w) > 3)

    if not new_words:
        return _accept_result()

    candidates = []
    for r in recent:
        if r.get('id') == opp.get('id'):
            continue
        rt = ((r.get('title') or '') + ' ' +
              (r.get('one_liner') or '')).lower()
        rwords = set(w for w in re.findall(r'\b\w+\b', rt) if len(w) > 3)
        if not rwords:
            continue
        union = new_words | rwords
        if not union:
            continue
        jaccard = len(new_words & rwords) / len(union)
        if jaccard >= min_jaccard:
            candidates.append((jaccard, r))

    candidates.sort(reverse=True, key=lambda x: x[0])
    candidates = candidates[:max_candidates]

    if len(candidates) < 2:
        # Düşük Jaccard, kavram-seviyesi dedup gereksiz
        return _accept_result()

    # Stage 2 — LLM check
    candidate_text = "\n".join(
        f"{i+1}. \"{c[1].get('title', '?')}\""
        f" — {(c[1].get('one_liner') or '')[:120]}"
        for i, c in enumerate(candidates)
    )

    prompt = f"""Yeni iş fırsatı:
Title: \"{opp.get('title', '')}\"
Özet: {(opp.get('one_liner') or '')[:200]}

Son {days} günde sistemde üretilmiş benzer adaylar:
{candidate_text}

Soru: Yeni fırsat KAVRAM SEVİYESİNDE bu mevcut fırsatların bir varyantı mı,
yoksa gerçekten yeni bir fikir mi?

KAVRAM aynıysa: aynı problemi farklı paketleyiş.
  Örnek: "TR-UK arbitrage in chemicals" + "TR-UK arbitrage in furniture" = aynı kavram
  Örnek: "AI compliance for BSA" + "AI compliance for AI Act" = aynı kavram (compliance wrapper)
  Örnek: "Cross-border SaaS for X" + "Cross-border SaaS for Y" = aynı kavram

FARKLI ise: farklı problem + farklı çözüm + farklı pazarlık aksı.
  Örnek: "TR-UK arbitrage" vs "DTC longevity supplements" = gerçekten farklı

SADECE valid JSON dön, başka yazı yok:

{{
  "is_echo": true | false,
  "similar_indices": [1, 3, 5],
  "concept_signature": "kavramın 5-7 kelimelik özü",
  "reason": "1 cümle"
}}

Kibar olma, ZORLU ol. Şüphe varsa is_echo=true. Sistem zaten 'tekrar' üretiminden mustarip."""

    try:
        response = llm_router.create(
            model=llm_router.get_model('daily'),  # Gemini Flash — ucuz
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text
        result = _parse_json(text)
    except Exception as e:
        logger.warning(f"Concept dedup LLM call failed: {e}")
        return _accept_result()

    if not result:
        return _accept_result()

    is_echo = bool(result.get('is_echo', False))
    similar_indices = result.get('similar_indices', []) or []

    similar = []
    for idx in similar_indices:
        try:
            i = int(idx)
            if 1 <= i <= len(candidates):
                similar.append(candidates[i - 1][1])
        except (ValueError, TypeError):
            continue

    similar_count = len(similar)

    if is_echo:
        if similar_count >= 4:
            recommendation = 'reject'
        elif similar_count >= 2:
            recommendation = 'downgrade'
        elif similar_count >= 1:
            recommendation = 'flag'
        else:
            recommendation = 'flag'  # is_echo true ama similar boş — şüpheli
    else:
        recommendation = 'accept'

    return {
        'is_echo': is_echo,
        'similar_count': similar_count,
        'similar': similar,
        'concept_signature': result.get('concept_signature', ''),
        'reason': result.get('reason', ''),
        'recommendation': recommendation,
    }


def _accept_result() -> dict:
    return {
        'is_echo': False,
        'similar_count': 0,
        'similar': [],
        'concept_signature': '',
        'reason': '',
        'recommendation': 'accept',
    }


def _parse_json(text: str) -> Optional[dict]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
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
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


# ─── Helper: apply downgrade ──────────────────────────────────────────

TIER_DOWNGRADE = {
    'VAY': 'FIRE',
    'FIRE': 'HIGH',
    'HIGH': 'MEDIUM',
    'MEDIUM': 'LOW',
    'LOW': 'LOW',
}


def apply_dedup_recommendation(opp: dict, dup_check: dict) -> tuple:
    """Apply dedup recommendation to opp dict.

    Returns (should_save: bool, modified_opp: dict).
    Mutates opp in-place to add echo metadata.
    """
    rec = dup_check.get('recommendation', 'accept')

    if rec == 'reject':
        return False, opp

    if rec == 'downgrade':
        original_tier = opp.get('tier', 'LOW')
        new_tier = TIER_DOWNGRADE.get(original_tier, 'LOW')
        opp['tier'] = new_tier
        opp['_echo_downgraded'] = True
        opp['_echo_original_tier'] = original_tier
        opp['_echo_signature'] = dup_check.get('concept_signature', '')
        opp['_echo_reason'] = dup_check.get('reason', '')

    if rec in ('downgrade', 'flag'):
        opp['_echo_flag'] = True
        opp['_echo_signature'] = dup_check.get('concept_signature', '')
        opp['_echo_reason'] = dup_check.get('reason', '')
        opp['_echo_similar_count'] = dup_check.get('similar_count', 0)

    return True, opp
