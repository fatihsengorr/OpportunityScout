#!/usr/bin/env python3
"""
OpportunityScout — CLI Entry Point

Usage:
    python -m src.cli scan [--tier 1|2|3]
    python -m src.cli digest
    python -m src.cli weekly
    python -m src.cli deep_dive "topic or OPP-ID"
    python -m src.cli score "your business idea description"
    python -m src.cli evolve
    python -m src.cli stats
    python -m src.cli portfolio [--top N]
    python -m src.cli sources
    python -m src.cli serve    # Start Telegram bot listener
    python -m src.cli init     # First-time setup
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('./logs/scout.log', mode='a')
    ]
)
logger = logging.getLogger("scout.cli")


def ensure_dirs():
    """Ensure required directories exist."""
    for d in ['./data', './logs', './exports']:
        Path(d).mkdir(parents=True, exist_ok=True)


async def cmd_scan(args):
    """Run a scan cycle."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    tier = getattr(args, 'tier', 1) or 1
    result = await engine.run_scan_cycle(tier=int(tier))
    print(json.dumps(result, indent=2))


async def cmd_digest(args):
    """Generate daily digest."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    await engine.generate_daily_digest()
    print("✅ Daily digest sent to Telegram")


async def cmd_weekly(args):
    """Generate weekly report."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    await engine.generate_weekly_report()
    print("✅ Weekly report sent to Telegram")


async def cmd_deep_dive(args):
    """Run deep dive on a topic."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    result = await engine.run_deep_dive(args.topic)
    print(json.dumps(result, indent=2, default=str))


async def cmd_score(args):
    """Score a business idea."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    result = await engine.score_idea(args.idea)
    
    if result.get("opportunities"):
        opp = result["opportunities"][0]
        print(f"\n{'='*60}")
        print(f"📊 OPPORTUNITY SCORECARD")
        print(f"{'='*60}")
        print(f"Title: {opp.get('title', 'N/A')}")
        print(f"Score: {opp.get('weighted_total', 0)}/185")
        print(f"Tier:  {opp.get('tier', 'N/A')}")
        print(f"\nOne-liner: {opp.get('one_liner', 'N/A')}")
        print(f"\nScores:")
        scores = opp.get('scores', {})
        for dim, data in sorted(scores.items()):
            score = data.get('score', 0) if isinstance(data, dict) else data
            reason = data.get('reason', '') if isinstance(data, dict) else ''
            bar = "█" * score + "░" * (10 - score)
            print(f"  {dim:25s} {bar} {score}/10  {reason[:50]}")
        print(f"\nWhy Now: {opp.get('why_now', 'N/A')}")
        print(f"First Move: {opp.get('first_move', 'N/A')}")
        print(f"Revenue Path: {opp.get('revenue_path', 'N/A')}")
        print(f"Risks: {', '.join(opp.get('risks', []))}")
        print(f"{'='*60}")
    else:
        print("Could not score this idea. Try providing more detail.")


async def cmd_evolve(args):
    """Run self-improvement cycle."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    changes = await engine.run_evolution_cycle()
    print(f"\n🧬 Evolution cycle complete: {len(changes)} changes")
    for change in changes:
        print(f"  • [{change.get('type')}] {change.get('description')}")


async def cmd_generate(args):
    """Generate novel business models from accumulated intelligence."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    focus = getattr(args, 'focus', None)
    count = getattr(args, 'count', 3) or 3

    print(f"\n💡 Generating {count} business models...")
    if focus:
        print(f"   Focus area: {focus}")
    print(f"   Using Claude Opus for creative synthesis...")
    print(f"   This may take 3-5 minutes.\n")

    result = await engine.generate_business_models(
        focus_area=focus, count=int(count)
    )

    models = result.get('models', [])
    if not models:
        print("❌ No models generated. Run more scan cycles first to accumulate data.")
        return

    gen_ctx = result.get('generation_context', {})
    print(f"{'='*70}")
    print(f"💡 BUSINESS MODEL GENERATION REPORT")
    print(f"{'='*70}")
    print(f"Models generated: {len(models)}")
    print(f"Signals analyzed: {gen_ctx.get('signals_analyzed', 0)}")
    print(f"Trends analyzed: {gen_ctx.get('trends_analyzed', 0)}")
    print(f"Blind spots considered: {gen_ctx.get('blind_spots_found', 0)}")
    print()

    for i, model in enumerate(models, 1):
        gen = model.get('generated_model', {})
        tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
            model.get('tier', ''), "📝"
        )
        print(f"{'─'*70}")
        print(f"MODEL {i}: {tier_emoji} {model.get('title', 'Untitled')}")
        print(f"Score: {model.get('weighted_total', 0)}/185 ({model.get('tier', '?')})")
        print(f"\n{model.get('one_liner', '')}")
        print(f"\nPROBLEM: {gen.get('problem', 'N/A')[:300]}")
        print(f"\nSOLUTION: {gen.get('solution', 'N/A')[:300]}")
        print(f"\nFIRST MOVE: {gen.get('first_move', 'N/A')}")
        print(f"\nID: {model.get('id', 'N/A')}\n")

    print(f"{'='*70}")
    print(f"All models saved and sent to Telegram.")


async def cmd_serendipity(args):
    """Run serendipity engine — discover opportunities outside known sectors."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    mode = getattr(args, 'mode', 'daily') or 'daily'

    if mode == 'deep':
        print(f"\n🎲 Running DEEP serendipity scan (Opus, all sectors)...")
        print(f"   This may take 5-8 minutes.\n")
        result = await engine.run_serendipity_weekly()
    else:
        print(f"\n🎲 Running daily serendipity scan (Sonnet, broad sweep)...")
        print(f"   This may take 2-3 minutes.\n")
        result = await engine.run_serendipity_daily()

    opps = result.get('opportunities', [])
    print(f"{'='*70}")
    print(f"🎲 SERENDIPITY RESULTS ({result.get('mode', '?')})")
    print(f"{'='*70}")
    print(f"Raw opportunities found: {result.get('raw_found', 0)}")
    print(f"Passed founder fit filter (≥5): {result.get('passed_filter', 0)}")
    print()

    if not opps:
        print("No opportunities passed the founder fit filter this time.")
        print("This is normal — most cross-sector findings won't match your profile.")
        return

    for i, opp in enumerate(opps, 1):
        tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
            opp.get('tier', ''), "📝"
        )
        print(f"{i}. {tier_emoji} {opp.get('title', '?')} — Score: {opp.get('weighted_total', 0)}")
        print(f"   {opp.get('one_liner', '')}")
        if opp.get('discovery_path'):
            print(f"   💡 Discovery: {opp['discovery_path'][:150]}")
        print(f"   Tags: {', '.join(opp.get('tags', []))}")
        print()

    print(f"{'='*70}")
    print(f"Results saved and sent to Telegram.")


async def cmd_localize(args):
    """Run localization scanner — Samwer/Rocket Internet lens."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    focus = getattr(args, 'focus', None)
    count = getattr(args, 'count', 5) or 5

    print(f"\n🌍 Running localization scan (Samwer lens)...")
    if focus:
        print(f"   Focus sector: {focus}")
    print(f"   Finding {count} proven models to localize into UK/Turkey...")
    print(f"   This may take 5-8 minutes.\n")

    result = await engine.run_localization_scan(
        focus_sector=focus, count=int(count)
    )

    opps = result.get('opportunities', [])
    print(f"{'='*70}")
    print(f"🌍 LOCALIZATION SCAN RESULTS")
    print(f"{'='*70}")
    print(f"Models analyzed: {result.get('models_analyzed', 0)}")
    print(f"Opportunities stored: {result.get('opportunities_stored', 0)}")
    print()

    if not opps:
        print("No localization opportunities found this cycle.")
        return

    for i, opp in enumerate(opps, 1):
        tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
            opp.get('tier', ''), "📝"
        )
        original = opp.get('original_model', {})
        gap = opp.get('gap_analysis', {})
        biz = opp.get('business_model', {})

        print(f"{'─'*70}")
        print(f"{i}. {tier_emoji} {opp.get('title', '?')}")
        print(f"   Score: {opp.get('weighted_total', 0)}/185 ({opp.get('tier', '?')})")
        print(f"\n   {opp.get('one_liner', '')}")
        print(f"\n   ORIGINAL: {original.get('company', '?')} ({original.get('country', '?')})")
        print(f"   Funding: {original.get('funding', 'N/A')}")
        print(f"   GAP: UK={gap.get('uk_status', '?')} | TR={gap.get('turkey_status', '?')}")
        print(f"   Revenue: {biz.get('revenue_type', 'N/A')} | {biz.get('pricing', 'N/A')}")
        print(f"   FIRST MOVE: {opp.get('first_move', 'N/A')}")
        print(f"   ID: {opp.get('id', 'N/A')}")
        print()

    print(f"{'='*70}")
    print(f"All results saved and sent to Telegram.")


def cmd_stats(args):
    """Show system statistics."""
    from .knowledge_base import KnowledgeBase
    kb = KnowledgeBase()
    stats = kb.get_stats()
    print(f"\n📈 OpportunityScout Statistics")
    print(f"{'='*40}")
    for key, value in stats.items():
        print(f"  {key:30s}: {value}")
    kb.close()


def cmd_portfolio(args):
    """Show top opportunities."""
    from .knowledge_base import KnowledgeBase
    kb = KnowledgeBase()
    top_n = getattr(args, 'top', 20) or 20
    opps = kb.get_top_opportunities(limit=int(top_n))
    
    if not opps:
        print("📭 No opportunities in portfolio yet. Run a scan first.")
        kb.close()
        return

    print(f"\n🏆 TOP {len(opps)} OPPORTUNITIES")
    print(f"{'='*80}")
    for i, opp in enumerate(opps, 1):
        tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
            opp.get('tier', ''), "📝"
        )
        print(
            f"{i:2d}. {tier_emoji} [{opp.get('weighted_total', 0):5.1f}] "
            f"{opp.get('title', 'Unknown')}"
        )
        print(f"     {opp.get('one_liner', '')}")
        print(f"     Status: {opp.get('status', 'new')} | "
              f"Sector: {opp.get('sector', 'N/A')} | "
              f"ID: {opp.get('id', 'N/A')}")
        print()
    kb.close()


def cmd_sources(args):
    """Show source list with performance."""
    from .knowledge_base import KnowledgeBase
    import yaml
    
    kb = KnowledgeBase()
    performance = kb.get_source_performance(days=30)
    perf_map = {p['source_name']: p for p in performance}

    try:
        with open('./config/sources.yaml') as f:
            sources = yaml.safe_load(f).get('sources', [])
    except FileNotFoundError:
        print("Sources config not found!")
        return

    print(f"\n📡 SOURCE REGISTRY ({len(sources)} sources)")
    print(f"{'='*100}")
    print(f"{'Name':40s} {'Tier':5s} {'Scans':6s} {'Opps':5s} {'Avg':5s} {'Best':5s} {'Errors':7s}")
    print(f"{'-'*100}")

    for source in sorted(sources, key=lambda s: s.get('tier', 9)):
        name = source['name']
        perf = perf_map.get(name, {})
        print(
            f"{name:40s} "
            f"T{source.get('tier', '?'):4s} "
            f"{perf.get('scan_count', 0):5d} "
            f"{perf.get('total_opportunities', 0):4d} "
            f"{perf.get('mean_score', 0):5.0f} "
            f"{perf.get('best_score', 0):5.0f} "
            f"{perf.get('total_errors', 0):6d}"
        )
    kb.close()


async def cmd_serve(args):
    """Start Telegram bot listener for interactive commands."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    app = engine.telegram.setup_command_handlers(engine)
    if app:
        print("🤖 Telegram bot is running. Press Ctrl+C to stop.")
        await app.run_polling()
    else:
        print("❌ Could not start Telegram bot. Check configuration.")


def cmd_init(args):
    """First-time setup: create directories, init DB, verify connections."""
    ensure_dirs()
    
    from .knowledge_base import KnowledgeBase
    kb = KnowledgeBase()
    stats = kb.get_stats()
    kb.close()

    print("🚀 OpportunityScout Initialized!")
    print(f"   Database: {stats}")
    print(f"   Directories: data/, logs/, exports/ created")
    print(f"\n   Next steps:")
    print(f"   1. Copy .env.example to .env and fill in your API keys")
    print(f"   2. Run: python -m src.cli scan --tier 1")
    print(f"   3. Check Telegram for results!")


def main():
    parser = argparse.ArgumentParser(
        description="OpportunityScout — Autonomous AI Business Intelligence Agent"
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Scan
    scan_parser = subparsers.add_parser('scan', help='Run a scan cycle')
    scan_parser.add_argument('--tier', type=int, default=1, choices=[1, 2, 3])

    # Digest
    subparsers.add_parser('digest', help='Generate daily digest')

    # Weekly
    subparsers.add_parser('weekly', help='Generate weekly report')

    # Deep dive
    dd_parser = subparsers.add_parser('deep_dive', help='Deep dive on a topic')
    dd_parser.add_argument('topic', type=str)

    # Score
    score_parser = subparsers.add_parser('score', help='Score a business idea')
    score_parser.add_argument('idea', type=str)

    # Evolve
    subparsers.add_parser('evolve', help='Run self-improvement cycle')

    # Generate business models
    gen_parser = subparsers.add_parser('generate', help='Generate novel business models')
    gen_parser.add_argument('--focus', type=str, default=None,
                           help='Focus area (e.g., "scan-to-bim", "fire-doors")')
    gen_parser.add_argument('--count', type=int, default=3,
                           help='Number of models to generate (default: 3)')

    # Serendipity — discover unexpected opportunities
    ser_parser = subparsers.add_parser('serendipity',
                                       help='Discover opportunities outside known sectors')
    ser_parser.add_argument('--mode', type=str, default='daily',
                           choices=['daily', 'deep'],
                           help='daily = Sonnet light scan, deep = Opus full analysis')

    # Localize — Samwer/Rocket Internet lens
    loc_parser = subparsers.add_parser('localize',
                                       help='Find proven models to copy into UK/Turkey')
    loc_parser.add_argument('--focus', type=str, default=None,
                           help='Focus sector (e.g., "proptech", "healthtech")')
    loc_parser.add_argument('--count', type=int, default=5,
                           help='Number of models to find (default: 5)')

    # Stats
    subparsers.add_parser('stats', help='Show system statistics')

    # Portfolio
    port_parser = subparsers.add_parser('portfolio', help='Show top opportunities')
    port_parser.add_argument('--top', type=int, default=20)

    # Sources
    subparsers.add_parser('sources', help='Show source performance')

    # Serve (Telegram bot)
    subparsers.add_parser('serve', help='Start Telegram bot listener')

    # Init
    subparsers.add_parser('init', help='First-time setup')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    ensure_dirs()

    # Route to command
    sync_commands = {
        'stats': cmd_stats,
        'portfolio': cmd_portfolio,
        'sources': cmd_sources,
        'init': cmd_init,
    }

    async_commands = {
        'scan': cmd_scan,
        'digest': cmd_digest,
        'weekly': cmd_weekly,
        'deep_dive': cmd_deep_dive,
        'score': cmd_score,
        'evolve': cmd_evolve,
        'generate': cmd_generate,
        'serendipity': cmd_serendipity,
        'localize': cmd_localize,
        'serve': cmd_serve,
    }

    if args.command in sync_commands:
        sync_commands[args.command](args)
    elif args.command in async_commands:
        asyncio.run(async_commands[args.command](args))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
