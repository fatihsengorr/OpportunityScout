# /deep-dive — Deep Research on a Specific Opportunity

Perform an exhaustive deep dive analysis on a specific opportunity or business idea. Uses Claude Opus for maximum analytical depth and web search for real-time market validation.

## Usage

- `/deep-dive OPP-20260324-001` — Deep dive on a specific opportunity from the portfolio
- `/deep-dive "AI-powered fire door inspection for UK social housing"` — Deep dive on a new idea

## What the deep dive covers

1. **Market Validation** — TAM/SAM/SOM with real numbers from web search
2. **Competitive Landscape** — 3-5 real competitors with actual pricing
3. **Technical Feasibility** — Exact tech stack, build cost, timeline
4. **Business Model** — Unit economics, pricing tiers, go-to-market
5. **Risk Assessment** — Top 3 kill risks, pre-mortem analysis
6. **90-Day Action Plan** — Week-by-week execution roadmap
7. **Financial Projections** — Month 3, 6, 12 revenue estimates

## Execution

```bash
cd /path/to/opportunity-scout
python -m src.cli deep_dive "your topic or OPP-ID here"
```

Results are stored in the knowledge base and sent to Telegram.
