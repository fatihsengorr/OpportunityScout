#!/usr/bin/env python3
"""
Retroactive Rescore — Re-score all existing opportunities with the new
Founder Fit Multiplier formula.

Usage:
    python3 -m scripts.rescore_all [--dry-run]

The new formula:
    base_total = sum(score_i * weight_i)  for 9 dimensions (excl. founder_fit)
    weighted_total = base_total * (founder_fit / 10.0)

Old formula (additive):
    weighted_total = sum(score_i * weight_i) for all 10 dimensions
    where founder_fit weight was 3.0
"""

import sqlite3
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scoring_utils import calculate_weighted_total, determine_tier


def rescore_all(db_path: str = "./data/opportunity_scout.db", dry_run: bool = False):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute("SELECT id, title, scores_json, weighted_total, tier FROM opportunities")
    rows = cursor.fetchall()

    print(f"Found {len(rows)} opportunities to rescore.\n")
    print(f"{'ID':<28} {'Old':>5} {'New':>5} {'Old Tier':<6} {'New Tier':<6} Title")
    print("-" * 110)

    changed = 0
    for row in rows:
        opp_id = row['id']
        title = row['title'] or ''
        old_total = row['weighted_total'] or 0
        old_tier = row['tier'] or 'LOW'

        scores_json = row['scores_json']
        if not scores_json:
            print(f"{opp_id:<28} {'N/A':>5} {'N/A':>5} {old_tier:<6} {'N/A':<6} {title[:50]}")
            continue

        scores = json.loads(scores_json)
        new_total = calculate_weighted_total(scores)
        new_tier = determine_tier(new_total)

        marker = ""
        if abs(new_total - old_total) > 0.1 or new_tier != old_tier:
            marker = " <-- CHANGED"
            changed += 1

        print(f"{opp_id:<28} {old_total:>5.1f} {new_total:>5.1f} {old_tier:<6} {new_tier:<6} {title[:50]}{marker}")

        if not dry_run and marker:
            cursor.execute(
                "UPDATE opportunities SET weighted_total = ?, tier = ?, updated_at = datetime('now') WHERE id = ?",
                (new_total, new_tier, opp_id)
            )

    # Also rescore generated_models
    cursor.execute("SELECT id, title, tags_json, weighted_total, tier FROM generated_models")
    model_rows = cursor.fetchall()
    if model_rows:
        print(f"\n\nFound {len(model_rows)} generated models to rescore.\n")
        print(f"{'ID':<28} {'Old':>5} {'New':>5} {'Old Tier':<6} {'New Tier':<6} Title")
        print("-" * 110)

        # Generated models store scores differently — check if they have scores_json-like data
        # Models don't have scores_json column, skip if no scoring data available

    if not dry_run:
        conn.commit()
        print(f"\n{'='*60}")
        print(f"DONE. Updated {changed} of {len(rows)} opportunities.")
    else:
        print(f"\n{'='*60}")
        print(f"DRY RUN. Would update {changed} of {len(rows)} opportunities.")
        print("Run without --dry-run to apply changes.")

    conn.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    db_path = "./data/opportunity_scout.db"

    # Allow custom db path
    for arg in sys.argv[1:]:
        if arg.endswith('.db'):
            db_path = arg

    rescore_all(db_path, dry_run=dry_run)
