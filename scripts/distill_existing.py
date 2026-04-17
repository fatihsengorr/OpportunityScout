"""
Wildcatter Faz 1 — Retroactive Distillation

Apply Pattern + Wow + Verifiability filters to existing top opportunities.
Goal: Find the "VAY" gems hidden in the existing 182-opportunity portfolio.

Strategy (cost-efficient):
  - All FIRE tier (5 ops): full pipeline
  - Top 15 HIGH tier (score >= 115): full pipeline
  - Total: ~20 opportunities × $0.06 = ~$1.20

Run on production:
  cd /opt/opportunity-scout && venv/bin/python scripts/distill_existing.py
"""

import os
import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scout_engine import ScoutEngine

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(name)s] %(message)s')
logger = logging.getLogger("distill")


def main():
    engine = ScoutEngine()
    cursor = engine.kb.conn.cursor()

    # Gather candidates
    cursor.execute("""
        SELECT id, title, sector, tier, weighted_total
        FROM opportunities
        WHERE (tier = 'FIRE') OR (tier = 'HIGH' AND weighted_total >= 115)
        ORDER BY weighted_total DESC
        LIMIT 25
    """)
    candidates = [dict(r) for r in cursor.fetchall()]

    logger.info(f"🧪 Retroactive distillation: {len(candidates)} candidates")
    print(f"\n{'='*70}")
    print(f"WILDCATTER FAZ 1 — RETROAKTİF DİSTİLASYON")
    print(f"Total candidates: {len(candidates)}")
    print(f"{'='*70}\n")

    results = []
    vay_count = 0
    wow_cand_count = 0

    for i, cand in enumerate(candidates, 1):
        opp_id = cand['id']
        title = cand['title'][:60]
        score = cand['weighted_total']
        tier = cand['tier']

        print(f"\n[{i}/{len(candidates)}] {tier} · {score:.0f} · {title}")
        print(f"  ID: {opp_id}")

        # Fetch full opportunity
        cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
        opp = dict(cursor.fetchone())

        # 1. Pattern match
        try:
            pattern_result = engine.patterns.match_and_save(opp_id, opp)
            pc = pattern_result.get('count', 0)
            pv = pattern_result.get('verdict', '?')
            print(f"  🧬 Patterns: {pc}/7 ({pv}, ×{pattern_result.get('bonus_multiplier')})")
        except Exception as e:
            logger.error(f"Pattern match failed: {e}")
            continue

        # 2. Wow threshold — only if high_match or wow_candidate
        wow_verdict = 'skipped'
        if pattern_result.get('verdict') in ('wow_candidate', 'high_match'):
            # Refresh opp after pattern save
            cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
            opp = dict(cursor.fetchone())
            try:
                wow_result = engine.wow.evaluate_and_save(opp_id, opp)
                wow_verdict = wow_result.get('verdict', '?')
                pass_count = wow_result.get('pass_count', 0)
                if wow_result.get('eligible'):
                    print(f"  🌟 Wow: {pass_count}/5 pass → {wow_verdict}")
                else:
                    print(f"  🌟 Wow: not eligible ({wow_result.get('reason', '')})")
            except Exception as e:
                logger.error(f"Wow eval failed: {e}")

        # 3. Verifiability (via validator)
        verif = None
        try:
            validation = engine.validator.validate(opp)
            verif = validation.get('verifiability_score', 0)
            print(f"  🔎 Validation: {validation.get('status')} · V{verif}/10")
        except Exception as e:
            logger.error(f"Validation failed: {e}")

        # Count
        if wow_verdict == 'VAY':
            vay_count += 1
        if pattern_result.get('verdict') == 'wow_candidate':
            wow_cand_count += 1

        results.append({
            'id': opp_id,
            'title': title,
            'tier': tier,
            'score': score,
            'pattern_count': pattern_result.get('count', 0),
            'pattern_verdict': pattern_result.get('verdict'),
            'wow_verdict': wow_verdict,
            'verifiability': verif,
        })

    # Summary
    print(f"\n{'='*70}")
    print(f"DISTİLASYON SONUÇ ÖZETİ")
    print(f"{'='*70}")
    print(f"  Toplam değerlendirilen: {len(results)}")
    print(f"  🌟 VAY tier: {vay_count}")
    print(f"  🎯 wow_candidate (pattern): {wow_cand_count}")
    print(f"")

    # Sort by pattern count desc, then score
    results.sort(key=lambda r: (r['pattern_count'], r['score']), reverse=True)
    print(f"TOP 10 (pattern count, score):")
    for r in results[:10]:
        vay_mark = "🌟" if r['wow_verdict'] == 'VAY' else ('🎯' if r['pattern_verdict'] == 'wow_candidate' else '  ')
        print(f"  {vay_mark} {r['id']} | P{r['pattern_count']}/7 | {r['tier']} · {r['score']:.0f} | {r['title']}")

    print(f"\n✅ Retroaktif distilasyon tamamlandı.")
    print(f"   Telegram'a /patterns OPP-XXX veya /wow OPP-XXX komutu ile detay görebilirsin.")


if __name__ == "__main__":
    main()
