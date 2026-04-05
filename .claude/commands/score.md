# /score — Score a Business Idea

Score any business idea against OpportunityScout's 10-dimension model. Get an instant assessment of how well an opportunity matches the founder's specific profile, assets, and market position.

## Usage

`/score "Description of your business idea"`

Example: `/score "Offering n8n automation consulting to UK SMEs, building custom workflows for £500-2000 per project, leveraging existing Upwork presence"`

## The 10 Dimensions

Each scored 1-10 with specific justification:

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| Founder Fit | ×3.0 | Match with specific skills, assets, network |
| AI Unlock | ×2.5 | Does AI create a genuine 10x improvement? |
| Time to Revenue | ×2.5 | How fast can this generate cash? |
| Capital Efficiency | ×2.0 | Can this start with minimal investment? |
| Market Timing | ×2.0 | Is there a regulatory/market inflection NOW? |
| Defensibility | ×1.5 | Moats, network effects, barriers |
| Scale Potential | ×1.5 | Can this become $10M+? |
| Geographic Leverage | ×1.5 | Cross-border advantage? |
| Competition Gap | ×1.0 | Clear gap in existing solutions? |
| Simplicity | ×1.0 | Can one person start this week? |

**Max Score: 185 points** | 🔥 FIRE ≥150 | ⭐ HIGH ≥120 | 📊 MEDIUM ≥90

## Execution

```bash
python -m src.cli score "your idea description here"
```
