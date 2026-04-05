# /generate — Invent Novel Business Models

Generate completely new business model ideas from OpportunityScout's accumulated intelligence. Unlike scanning (which finds existing opportunities), this module INVENTS new businesses by cross-referencing market signals, trends, blind spots, and the founder's unique capabilities.

## How it works

1. **Gathers** all accumulated signals, trends, cross-pollination insights, and blind spots from the knowledge base
2. **Sends** everything to Claude Opus with a creative synthesis prompt + the founder's capability map
3. **Opus invents** genuinely novel business models grounded in real market data
4. **Each model gets scored** through the standard 10-dimension pipeline (185 points)
5. **Web validation** confirms key assumptions via live search
6. **Results** are stored in the knowledge base and sent to Telegram

## Usage

```bash
# Generate 3 business models across all domains
python -m src.cli generate

# Generate with a specific focus
python -m src.cli generate --focus "scan-to-bim"
python -m src.cli generate --focus "fire-doors"
python -m src.cli generate --focus "cross-border-arbitrage"

# Generate more or fewer models
python -m src.cli generate --count 5
python -m src.cli generate --focus "digital-twin" --count 2
```

## From Telegram

```
/generate              → Generate 3 models, all domains
/generate scan-to-bim  → Focus on Scan-to-BIM
/generate fire-doors   → Focus on fire door market
```

## What makes this different from scanning

The scanner asks: "What opportunities already exist out there?"
The generator asks: "What business should we build that nobody else can see?"

The generator traces every idea back to specific signals in the accumulated data — it's not random brainstorming. It connects dots across industries, regulations, and capabilities that only become visible when you have weeks of accumulated intelligence.

## Cost

Each generation cycle costs approximately $2-4 (Opus for creative synthesis + Sonnet for scoring + web search for validation). Run it weekly for best results.
