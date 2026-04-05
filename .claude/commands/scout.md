# /scout — Run OpportunityScout Scan Cycle

Run the OpportunityScout autonomous scanning engine. This executes a full intelligence gathering cycle:

1. Scans all Tier 1 sources (news, tenders, social media, tech)
2. Sends content to Claude API for opportunity extraction and scoring
3. Stores results in the knowledge base
4. Sends Telegram alerts for FIRE and HIGH tier opportunities
5. Generates cross-pollination insights

## Usage

Just run `/scout` for a standard Tier 1 scan, or specify:
- `/scout tier1` — High-signal daily sources (default)
- `/scout tier2` — Medium-signal weekly sources
- `/scout tier3` — Deep-signal monthly sources
- `/scout all` — Full scan across all tiers

## Execution

```bash
cd /path/to/opportunity-scout
python -m src.cli scan --tier 1
```

After scanning, review results with:
```bash
python -m src.cli portfolio --top 10
```

## What to look for

After a scan, check Telegram for:
- 🔥 FIRE alerts (score ≥150) — act immediately
- ⭐ HIGH alerts (score ≥120) — schedule deep dive
- 📊 Daily digest — overview of all findings

If you see a promising opportunity, deep dive with:
```bash
python -m src.cli deep_dive "OPP-XXXXXXXX-XXX"
```
