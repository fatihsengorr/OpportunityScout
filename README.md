# 🔍 OpportunityScout

**An autonomous AI business intelligence agent that never sleeps.**

OpportunityScout continuously scans the internet, social media, government tenders, regulatory changes, and emerging technology trends to discover, score, and deliver high-value business opportunities — tailored specifically to your unique skills, assets, and market position.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────┐
│                 CLAUDE CODE (Brain)                   │
│  ┌────────────────────────────────────────────┐      │
│  │          OpportunityScout Engine            │      │
│  │  • 35+ data sources across 3 tiers         │      │
│  │  • Claude API analysis (Sonnet + Opus)     │      │
│  │  • 10-dimension scoring (185-point scale)  │      │
│  │  • Self-improvement evolution loop         │      │
│  │  • Cross-pollination insight engine        │      │
│  └────────────────────────────────────────────┘      │
│              ▲              │                          │
│              │              ▼                          │
│  ┌───────────────┐  ┌──────────────┐                 │
│  │ Knowledge Base│  │ Claude API   │                 │
│  │  (SQLite)     │  │ (+ web_search│                 │
│  │  • Opps DB    │  │   tool)      │                 │
│  │  • Signals    │  └──────────────┘                 │
│  │  • Trends     │                                    │
│  │  • Evolution  │                                    │
│  └───────────────┘                                    │
└───────────────┬──────────────────────────────────────┘
                │
   ┌────────────┼────────────┐
   ▼            ▼            ▼
┌────────┐ ┌─────────┐ ┌──────────┐
│  n8n   │ │Telegram │ │  CLI     │
│Scheduler│ │  Bot    │ │ Commands │
│ (Cron) │ │(Alerts) │ │          │
└────────┘ └─────────┘ └──────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))
- Telegram Bot token (create via [@BotFather](https://t.me/BotFather))
- Docker & Docker Compose (for production deployment)

### 1. Clone & Setup

```bash
git clone <your-repo-url> opportunity-scout
cd opportunity-scout

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys
```

### 2. Initialize

```bash
python -m src.cli init
```

### 3. Run Your First Scan

```bash
# Run a Tier 1 scan (high-signal sources)
python -m src.cli scan --tier 1

# Check what was found
python -m src.cli portfolio --top 10

# Score a specific idea
python -m src.cli score "AI-powered UK Building Safety Act compliance auditing"
```

### 4. Start Telegram Bot (Interactive Mode)

```bash
python -m src.cli serve
```

Then message your bot on Telegram:
- `/scout` — Run a scan
- `/portfolio` — View top opportunities
- `/stats` — System statistics
- `/help` — All commands

### 5. Deploy with Docker (Production)

```bash
# Build and start all services
docker-compose up -d

# Import n8n workflows
# Go to http://localhost:5678 and import:
#   - n8n/daily_scan.json
#   - n8n/weekly_deep_dive.json
```

---

## 📊 How Scoring Works

Every opportunity is scored on **10 dimensions**, each weighted by importance:

| Dimension | Weight | Max | Description |
|-----------|--------|-----|-------------|
| Founder Fit | ×3.0 | 30 | Match with your specific skills, assets, network |
| AI Unlock | ×2.5 | 25 | Does AI create a genuine 10x improvement? |
| Time to Revenue | ×2.5 | 25 | How fast can this generate real cash? |
| Capital Efficiency | ×2.0 | 20 | Can this start with minimal investment? |
| Market Timing | ×2.0 | 20 | Regulatory/market inflection point NOW? |
| Defensibility | ×1.5 | 15 | Moats, network effects, barriers |
| Scale Potential | ×1.5 | 15 | Can this become $10M+? |
| Geographic Leverage | ×1.5 | 15 | Cross-border Turkey↔UK↔UAE advantage? |
| Competition Gap | ×1.0 | 10 | Clear gap in existing solutions? |
| Simplicity | ×1.0 | 10 | Can one person start this week? |

**Total: 185 points maximum**

### Tier Thresholds

| Tier | Score | Action |
|------|-------|--------|
| 🔥 FIRE | ≥150 | Drop everything, act immediately |
| ⭐ HIGH | ≥120 | Schedule deep dive this week |
| 📊 MEDIUM | ≥90 | Monitor, may improve with timing |
| 📝 LOW | <90 | Log for reference |

---

## 📡 Data Sources (35+)

### Tier 1 — Daily Scans
- UK Government tenders (Find a Tender, Contracts Finder)
- Construction news (Construction Enquirer, Building, PBC Today)
- Property/BTR (Property Week, CoStar)
- Building Safety Act updates
- Tech/AI (TechCrunch, Hacker News, Product Hunt)
- Turkish manufacturing/export news
- Reddit (r/entrepreneur, r/SaaS, r/UKBusiness)

### Tier 2 — Weekly Scans
- UK Companies House new registrations
- Administration/insolvency notices (gap detection)
- Upwork trending categories
- Y Combinator batch analysis
- Innovate UK funding calls
- Net Zero/MEES regulatory updates
- BTR furniture competitor tracking

### Tier 3 — Monthly Deep Scans
- Academic papers (arXiv)
- Patent filings
- Government policy papers (DLUHC)
- EU AI Act implementation
- Trade shows & exhibitions
- Azerbaijan/UAE construction markets

---

## 🧬 Self-Improvement Loop

Every week, the scout runs an evolution cycle:

1. **Source Audit** — Which sources produce the best opportunities? Upweight stars, flag underperformers.
2. **Scoring Calibration** — If you've provided feedback, detect and correct dimension biases.
3. **Pattern Detection** — What themes keep clustering? Emerging opportunity areas?
4. **Blind Spot Detection** — Which of your capabilities are underexploited?
5. **Evolution Log** — Every change is documented for transparency.

Your feedback directly improves the system. Rate opportunities in Telegram or via:
```bash
python -m src.cli feedback OPP-20260324-001 --rating 5 --notes "This is excellent"
```

---

## 🔧 Claude Code Integration

### Custom Commands

When using Claude Code in the project directory, these slash commands are available:

| Command | Description |
|---------|-------------|
| `/scout` | Run a full scanning cycle |
| `/deep-dive` | Deep research on a specific opportunity |
| `/score` | Score a business idea against the model |

### Prompt File

The `CLAUDE_CODE_MASTER_PROMPT.md` file contains the complete system prompt for Claude Code. Load it as context when working on the project:

```bash
claude --prompt CLAUDE_CODE_MASTER_PROMPT.md
```

---

## 📁 Project Structure

```
opportunity-scout/
├── CLAUDE_CODE_MASTER_PROMPT.md    # Brain — main orchestration prompt
├── SYSTEM_PROMPT.md                # Analysis engine system prompt
├── .claude/commands/               # Claude Code slash commands
│   ├── scout.md
│   ├── deep-dive.md
│   └── score.md
├── config/
│   ├── config.yaml                 # Main configuration
│   ├── sources.yaml                # 35+ data sources
│   └── founder_profile.yaml        # Your scoring profile
├── src/
│   ├── cli.py                      # CLI entry point
│   ├── scout_engine.py             # Main orchestrator
│   ├── web_scanner.py              # Multi-source content fetcher
│   ├── opportunity_scorer.py       # Claude API analysis engine
│   ├── knowledge_base.py           # SQLite persistence
│   ├── telegram_bot.py             # Telegram integration
│   └── self_improver.py            # Evolution engine
├── n8n/
│   ├── daily_scan.json             # Daily cron workflow
│   └── weekly_deep_dive.json       # Weekly deep dive + evolution
├── docker-compose.yml              # Full stack deployment
├── Dockerfile                      # Agent container
├── requirements.txt                # Python dependencies
└── .env.example                    # Environment template
```

---

## 🔐 Security Notes

- API keys are stored in `.env` (gitignored)
- The system only READS web content — no write operations to external services
- Telegram chat ID restricts output to your personal chat
- SQLite database is local — no cloud data storage
- All Claude API calls go through official Anthropic API

---

## 📈 Customization

### Adding New Sources

Edit `config/sources.yaml`:

```yaml
- name: "Your New Source"
  type: web_search  # or rss, reddit, api
  query: "your search query here"
  tier: 1  # 1=daily, 2=weekly, 3=monthly
  tags: [relevant, tags, here]
  signal_score: 7
  scan_frequency: daily
```

### Adjusting Scoring Weights

Edit `config/config.yaml` under `scoring.weights`. The evolution engine will also suggest adjustments based on your feedback.

### Modifying the Founder Profile

Edit `config/founder_profile.yaml` to add new competencies, assets, or sweet spots. This directly impacts Founder Fit scoring.

---

## 🗺️ Roadmap

- [ ] Open Brain MCP integration (persistent thought storage)
- [ ] Email digest option (alongside Telegram)
- [ ] Web dashboard (React) for visual portfolio management
- [ ] Multi-language source scanning (Turkish news)
- [ ] Automated competitor monitoring alerts
- [ ] Integration with UK planning portal API
- [ ] Voice summary via ElevenLabs
- [ ] WhatsApp Business integration

---

## 💡 Philosophy

> "The best opportunities are hiding in plain sight at the intersection of domains most people don't inhabit simultaneously."

OpportunityScout is built on the belief that a person who understands Turkish manufacturing, UK building regulations, AI automation, AND cross-border trade has an information advantage that no single-domain expert can match. The scout's job is to surface where those domains collide — and score the collision.

---

*Built with Claude API, Python, n8n, and a refusal to accept that opportunity discovery should be manual.*
