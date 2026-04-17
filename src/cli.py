#!/usr/bin/env python3
"""
OpportunityScout — CLI Entry Point (Intelligence Mesh v2)

Usage:
    python -m src.cli scan [--tier 1|2|3|all]
    python -m src.cli digest
    python -m src.cli weekly
    python -m src.cli deep_dive "topic or OPP-ID"
    python -m src.cli score "your business idea description"
    python -m src.cli generate [--focus AREA] [--count N]
    python -m src.cli serendipity [--mode daily|deep]
    python -m src.cli localize [--focus SECTOR] [--count N]
    python -m src.cli explore [--capability X] [--industry Y] [--count N]
    python -m src.cli deadlines
    python -m src.cli competitors [--opportunity OPP-ID]
    python -m src.cli crosspoll
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
    tier_val = getattr(args, 'tier', '1') or '1'

    if str(tier_val) in ('0', 'all'):
        # --tier all means ALL tiers + comprehensive email report
        print(f"\n{'='*60}")
        print(f"🔍 FULL SCAN — All Tiers (1+2+3)")
        print(f"{'='*60}")
        result = await engine.run_full_scan(tiers=[1, 2, 3])
        combined_stats = result.get('combined_stats', {})
        print(f"\n{'='*60}")
        print(f"✅ ALL TIERS COMPLETE")
        print(f"  Opportunities: {combined_stats.get('opportunities_found', 0)}")
        print(f"  FIRE alerts: {combined_stats.get('fire_alerts', 0)}")
        print(f"  Duration: {result.get('total_duration', 0):.0f}s")
        print(f"  📧 Scan report email sent!")
        print(f"{'='*60}")
    else:
        result = await engine.run_scan_cycle(tier=int(tier_val))
        print(json.dumps(result, indent=2, default=str))


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


async def cmd_patterns(args):
    """Evaluate 7 pattern inventory for an opportunity."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    result = await engine.run_pattern_match(args.opp_id)
    if result.get('error'):
        print(f"❌ Error: {result['error']}")
    else:
        p = result.get('patterns', {})
        print(f"\n✅ Pattern match for {args.opp_id}")
        print(f"  Count: {p.get('count', 0)}/7")
        print(f"  Verdict: {p.get('verdict', '?')}")
        print(f"  Bonus: ×{p.get('bonus_multiplier', 1.0)}")
        for pat in p.get('patterns', []):
            icon = '✅' if pat['matched'] else '❌'
            print(f"  {icon} P{pat['id']}. {pat['name']} ({pat['confidence']:.0%})")


async def cmd_wow(args):
    """Evaluate 5-criterion Vay (Wow) threshold."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    result = await engine.run_wow_eval(args.opp_id)
    if result.get('error'):
        print(f"❌ Error: {result['error']}")
    else:
        w = result.get('wow', {})
        if not w.get('eligible'):
            print(f"\n○ Not eligible for wow evaluation: {w.get('reason', 'ineligible')}")
        else:
            print(f"\n✅ Wow threshold for {args.opp_id}")
            print(f"  Pass count: {w.get('pass_count', 0)}/5")
            print(f"  Verdict: {w.get('verdict', '?')}")
            for c in w.get('criteria', []):
                icon = '✅' if c['pass'] else '❌'
                print(f"  {icon} {c['name']} ({c['confidence']:.0%})")


async def cmd_signals(args):
    """Scan external signal sources (Google Jobs, Crunchbase)."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    result = await engine.run_signal_scan()
    print(f"\n✅ External signal scan complete")
    for source, count in result.items():
        print(f"  {source}: {count} new signals")


async def cmd_consensus(args):
    """Run consensus check on an opportunity (2nd-opinion re-score)."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    result = await engine.run_consensus(args.opp_id)
    if result.get('error'):
        print(f"❌ Error: {result['error']}")
    else:
        c = result.get('consensus', {})
        p = c.get('primary', {})
        s = c.get('secondary', {}) or {}
        print(f"\n✅ Consensus check for {args.opp_id}")
        print(f"  Primary:   {p.get('score', 0):.0f}/155 ({p.get('tier', '?')})")
        print(f"  Secondary: {s.get('score', 0):.0f}/155 ({s.get('tier', '?')})")
        print(f"  Median: {c.get('median_score', 0):.0f}")
        print(f"  Divergence: {c.get('divergence', 0):.0f}")
        print(f"  Disputed: {c.get('disputed', False)}")
        print(f"  Verdict: {c.get('verdict', '?')}")


async def cmd_validate(args):
    """Validate factual claims in an opportunity."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    result = await engine.run_validation(args.opp_id)
    if result.get('error'):
        print(f"❌ Error: {result['error']}")
    else:
        v = result.get('validation', {})
        print(f"\n✅ Validation complete for {args.opp_id}")
        print(f"  Status: {v.get('status', '?')}")
        print(f"  Confidence: {v.get('confidence', 0):.0%}")
        print(f"  Claims checked: {len(v.get('claims', []))}")
        for flag in v.get('flags', []):
            print(f"  {flag}")


async def cmd_finance(args):
    """Generate financial model for an opportunity."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    result = await engine.run_financial_model(args.opp_id)
    if result.get('error'):
        print(f"❌ Error: {result['error']}")
    else:
        m = result.get('model', {})
        ue = m.get('unit_economics', {})
        realistic = m.get('projections', {}).get('realistic', {})
        print(f"\n✅ Financial model generated for {args.opp_id}")
        print(f"  Verdict: {m.get('verdict', '?')}")
        print(f"  LTV/CAC: {ue.get('ltv_cac_ratio', 0):.1f}x")
        print(f"  Break-even: month {realistic.get('break_even_month', '—')}")
        print(f"  Capital required: £{realistic.get('capital_required_gbp', 0):,.0f}")


async def cmd_action_kit(args):
    """Generate action kit for an opportunity."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    result = await engine.run_action_kit(args.opp_id)
    if result.get('error'):
        print(f"❌ Error: {result['error']}")
    elif result.get('_parse_error'):
        print("⚠️ JSON parse error — see logs")
    else:
        kit = result.get('kit', {})
        print(f"\n✅ Action kit generated for {args.opp_id}")
        print(f"  {len(kit.get('plan_30day', []))} weekly milestones")
        print(f"  {len(kit.get('discovery_questions', []))} discovery questions")
        print(f"  {len(kit.get('known_competitors', []))} known competitors to check")
        print(f"  Delivered via Telegram + email.")


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
        print(f"Score: {opp.get('weighted_total', 0)}/155")
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
        print(f"Score: {model.get('weighted_total', 0)}/155 ({model.get('tier', '?')})")
        print(f"\n{model.get('one_liner', '')}")
        print(f"\nPROBLEM: {gen.get('problem', 'N/A')[:300]}")
        print(f"\nSOLUTION: {gen.get('solution', 'N/A')[:300]}")
        print(f"\nFIRST MOVE: {gen.get('first_move', 'N/A')}")
        print(f"\nID: {model.get('id', 'N/A')}\n")

    print(f"{'='*70}")
    print(f"All models saved and sent to Telegram.")


async def cmd_horizon(args):
    """Run horizon scanner — unbounded 7-lens discovery engine."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    mode = getattr(args, 'mode', 'daily') or 'daily'

    if mode == 'deep':
        print(f"\n🔭 Running DEEP horizon scan (Opus, all 7 lenses)...")
        print(f"   This may take 10-15 minutes.\n")
        result = await engine.run_horizon_weekly()
    else:
        print(f"\n🔭 Running daily horizon scan (Sonnet, 3 rotating lenses)...")
        print(f"   This may take 3-5 minutes.\n")
        result = await engine.run_horizon_daily()

    opps = result.get('opportunities', [])
    lens_results = result.get('lens_results', {})
    frontiers = result.get('new_frontiers', [])

    print(f"{'='*70}")
    print(f"🔭 HORIZON SCAN RESULTS")
    print(f"{'='*70}")
    print(f"Total opportunities: {len(opps)}")
    for lens, info in lens_results.items():
        if isinstance(info, dict) and 'found' in info:
            print(f"  {lens}: {info['found']} found ({info.get('fire', 0)} FIRE, {info.get('high', 0)} HIGH)")
    print(f"New frontiers discovered: {len(frontiers)}")
    print()

    if frontiers:
        print("🌱 NEW FRONTIERS (self-expanding search space):")
        for f in frontiers:
            print(f"  → {f}")
        print()

    for i, opp in enumerate(opps, 1):
        tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
            opp.get('tier', ''), "📝"
        )
        print(f"{i}. {tier_emoji} {opp.get('title', '?')} — {opp.get('weighted_total', 0)}/155")
        print(f"   {opp.get('one_liner', '')}")
        if opp.get('discovery_path'):
            print(f"   💡 {opp['discovery_path'][:150]}")
        print(f"   Sector: {opp.get('sector', 'N/A')} | Tags: {', '.join(opp.get('tags', []))}")
        print()

    print(f"{'='*70}")


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
        print(f"   Score: {opp.get('weighted_total', 0)}/155 ({opp.get('tier', '?')})")
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


async def cmd_explore(args):
    """Run capability-first exploration — discover opportunities from founder's skills."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    capability = getattr(args, 'capability', None)
    industry = getattr(args, 'industry', None)
    count = getattr(args, 'count', 3) or 3

    print(f"\n🔭 Running capability exploration...")
    if capability:
        print(f"   Capability: {capability}")
    if industry:
        print(f"   Industry: {industry}")
    if not capability and not industry:
        print(f"   Auto-selecting {count} least explored capability×industry pairs...")
    print(f"   This may take 3-5 minutes.\n")

    result = await engine.run_exploration(
        capability=capability, industry=industry, count=int(count)
    )

    explorations = result.get('explorations', [])
    opportunities = result.get('opportunities', [])

    print(f"{'='*70}")
    print(f"🔭 CAPABILITY EXPLORATION RESULTS")
    print(f"{'='*70}")
    print(f"Explorations run: {len(explorations)}")
    print(f"Total opportunities: {len(opportunities)}")
    print()

    for r in explorations:
        cap = r.get('capability', '?')
        ind = r.get('industry', '?')
        opps = r.get('opportunities', [])
        neg = r.get('negative_evidence', '')

        print(f"{'─'*70}")
        print(f"🔬 {cap} × {ind}")
        if opps:
            for opp in opps:
                tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
                    opp.get('tier', ''), "📝"
                )
                print(f"   {tier_emoji} {opp.get('title', '?')} — {opp.get('weighted_total', 0)}/155")
                print(f"      {opp.get('one_liner', '')}")
        elif neg:
            print(f"   ⚠️ Negative evidence: {neg[:200]}")
        else:
            print(f"   No opportunities found")
        print()

    print(f"{'='*70}")
    print(f"Results saved and sent to Telegram.")


async def cmd_deadlines(args):
    """Check regulatory deadlines and timing windows."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()

    print(f"\n📅 Checking regulatory deadlines...\n")
    result = await engine.check_deadlines()

    report = engine.temporal.get_deadline_report()
    print(report)
    print(f"\n{'='*40}")
    print(f"Total alerts: {result.get('count', 0)}")


async def cmd_competitors(args):
    """Run competitive intelligence scan."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    opp_id = getattr(args, 'opportunity', None)

    print(f"\n🏢 Running competitive scan...")
    if opp_id:
        print(f"   Targeting opportunity: {opp_id}")
    print(f"   This may take 3-5 minutes.\n")

    result = await engine.run_competitive_scan(opportunity_id=opp_id)

    print(f"{'='*70}")
    print(f"🏢 COMPETITIVE INTELLIGENCE RESULTS")
    print(f"{'='*70}")
    print(f"New competitors identified: {result.get('new_competitors_identified', 0)}")
    print(f"Competitors monitored: {result.get('competitors_monitored', 0)}")
    print(f"Opportunity signals: {result.get('signals_found', 0)}")

    report = engine.competitors.get_competitor_report()
    print(f"\n{report}")


async def cmd_crosspoll(args):
    """Run cross-sector connection analysis."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()

    print(f"\n🔗 Running cross-pollination analysis...")
    print(f"   Finding connections between opportunities from different sectors...")
    print(f"   This may take 5-8 minutes.\n")

    result = await engine.run_cross_pollination()

    connections = result.get('connections', [])
    hybrids = result.get('hybrid_opportunities', [])

    print(f"{'='*70}")
    print(f"🔗 CROSS-POLLINATION RESULTS")
    print(f"{'='*70}")
    print(f"Connections found: {len(connections)}")
    print(f"Hybrid opportunities: {len(hybrids)}")
    print()

    for i, conn in enumerate(connections, 1):
        sectors = ', '.join(conn.get('sectors', []))
        print(f"{'─'*70}")
        print(f"{i}. [{conn.get('connection_type', '?')}] {sectors}")
        print(f"   Insight: {conn.get('insight', '')[:200]}")
        print(f"   Hybrid: {conn.get('hybrid_opportunity', '')[:200]}")
        print()

    if hybrids:
        print(f"\n{'─'*70}")
        print(f"HYBRID OPPORTUNITIES:")
        for opp in hybrids:
            tier_emoji = {"FIRE": "🔥", "HIGH": "⭐", "MEDIUM": "📊"}.get(
                opp.get('tier', ''), "📝"
            )
            print(f"  {tier_emoji} {opp.get('title', '?')} — {opp.get('weighted_total', 0)}/155")
            print(f"     {opp.get('one_liner', '')}")

    print(f"\n{'='*70}")
    print(f"Results saved and sent to Telegram.")


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


def cmd_serve(args):
    """Start Telegram bot listener for interactive commands."""
    from .scout_engine import ScoutEngine
    engine = ScoutEngine()
    app = engine.telegram.setup_command_handlers(engine)
    if app:
        print("🤖 Telegram bot is running. Press Ctrl+C to stop.")
        app.run_polling()
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
    scan_parser.add_argument('--tier', type=str, default='1', choices=['1', '2', '3', '0', 'all'],
                             help='1/2/3 for specific tier, 0 or all for all tiers')

    # Digest
    subparsers.add_parser('digest', help='Generate daily digest')

    # Weekly
    subparsers.add_parser('weekly', help='Generate weekly report')

    # Deep dive
    dd_parser = subparsers.add_parser('deep_dive', help='Deep dive on a topic')
    dd_parser.add_argument('topic', type=str)

    # Action kit — 30-day action plan for an opportunity
    ak_parser = subparsers.add_parser('action_kit',
                                       help='Generate action kit for an opportunity')
    ak_parser.add_argument('opp_id', type=str,
                           help='Opportunity ID (e.g., OPP-20260416-abc123)')

    # Finance — unit economics + 12-month projection
    fin_parser = subparsers.add_parser('finance',
                                        help='Generate financial model for an opportunity')
    fin_parser.add_argument('opp_id', type=str,
                            help='Opportunity ID (e.g., OPP-20260416-abc123)')

    # Validate — claim validation with web search
    val_parser = subparsers.add_parser('validate',
                                        help='Validate factual claims in an opportunity')
    val_parser.add_argument('opp_id', type=str,
                            help='Opportunity ID')

    # Consensus — 2nd-opinion score from independent model
    cons_parser = subparsers.add_parser('consensus',
                                         help='Get 2nd-opinion score from independent model')
    cons_parser.add_argument('opp_id', type=str,
                             help='Opportunity ID')

    # Signals — external signal scan (Google Jobs, Crunchbase)
    subparsers.add_parser('signals',
                          help='Scan external signals (hiring, funding)')

    # Patterns — 7 pattern inventory evaluation
    pat_parser = subparsers.add_parser('patterns',
                                        help="Evaluate Fatih's 7 pattern inventory")
    pat_parser.add_argument('opp_id', type=str, help='Opportunity ID')

    # Wow — 5-criterion Vay threshold
    wow_parser = subparsers.add_parser('wow',
                                        help='Evaluate Vay (Wow) threshold for FIRE candidate')
    wow_parser.add_argument('opp_id', type=str, help='Opportunity ID')

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

    # Horizon — unbounded 7-lens discovery
    hor_parser = subparsers.add_parser('horizon',
                                       help='Unbounded discovery — find next Uber/Amazon')
    hor_parser.add_argument('--mode', type=str, default='daily',
                           choices=['daily', 'deep'],
                           help='daily = 3 lenses Sonnet, deep = all 7 lenses Opus')

    # Explore — capability-first discovery
    exp_parser = subparsers.add_parser('explore',
                                       help='Explore opportunities from founder capabilities')
    exp_parser.add_argument('--capability', type=str, default=None,
                           help='Specific capability cluster (e.g., "it_infrastructure")')
    exp_parser.add_argument('--industry', type=str, default=None,
                           help='Specific adjacent industry (e.g., "managed_soc")')
    exp_parser.add_argument('--count', type=int, default=3,
                           help='Number of explorations to run (default: 3)')

    # Localize — Samwer/Rocket Internet lens
    loc_parser = subparsers.add_parser('localize',
                                       help='Find proven models to copy into UK/Turkey')
    loc_parser.add_argument('--focus', type=str, default=None,
                           help='Focus sector (e.g., "proptech", "healthtech")')
    loc_parser.add_argument('--count', type=int, default=5,
                           help='Number of models to find (default: 5)')

    # Deadlines — regulatory calendar
    subparsers.add_parser('deadlines', help='Check regulatory deadlines')

    # Competitors — competitive intelligence
    comp_parser = subparsers.add_parser('competitors',
                                        help='Run competitive intelligence scan')
    comp_parser.add_argument('--opportunity', type=str, default=None,
                            help='Specific opportunity ID to analyze')

    # Cross-pollination — find connections
    subparsers.add_parser('crosspoll', help='Find cross-sector connections')

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
        'serve': cmd_serve,
    }

    async_commands = {
        'scan': cmd_scan,
        'digest': cmd_digest,
        'weekly': cmd_weekly,
        'deep_dive': cmd_deep_dive,
        'action_kit': cmd_action_kit,
        'finance': cmd_finance,
        'validate': cmd_validate,
        'consensus': cmd_consensus,
        'signals': cmd_signals,
        'patterns': cmd_patterns,
        'wow': cmd_wow,
        'score': cmd_score,
        'evolve': cmd_evolve,
        'generate': cmd_generate,
        'serendipity': cmd_serendipity,
        'horizon': cmd_horizon,
        'localize': cmd_localize,
        'explore': cmd_explore,
        'deadlines': cmd_deadlines,
        'competitors': cmd_competitors,
        'crosspoll': cmd_crosspoll,
    }

    if args.command in sync_commands:
        sync_commands[args.command](args)
    elif args.command in async_commands:
        asyncio.run(async_commands[args.command](args))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
