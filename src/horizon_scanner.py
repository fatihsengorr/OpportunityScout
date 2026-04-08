"""
OpportunityScout — Horizon Scanner (7-Lens Unbounded Discovery Engine)

The "see what nobody sees" module. Unlike Serendipity Engine (which operates
within predefined sector rotations), Horizon Scanner has NO sector constraints.

7 Lenses — each a different mental model for how billion-dollar opportunities are born:

  Lens 1: ANALOGY TRANSFER — What succeeded elsewhere that doesn't exist here?
  Lens 2: FRICTION MAPPER — Where do people waste the most time/money?
  Lens 3: CONVERGENCE DETECTOR — Where are 2+ macro trends colliding?
  Lens 4: PLATFORM GAP — What 2-sided marketplaces are missing?
  Lens 5: REGULATION ARBITRAGE — What new rules just created captive demand?
  Lens 6: DYING INDUSTRY AUTOPSY — What's declining and what replaces it?
  Lens 7: FOUNDER ASSET INVERSION — What if the founder's assets ARE the product?

Self-expanding: when a lens discovers a new sector, it auto-generates search
queries for future runs. The system's search space grows organically.

Cost: ~$1/day (3 lenses, Sonnet) + ~$6/week (all 7, Opus) = ~$54/month
"""

import json
import logging
import os
import time
import re
import yaml
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic
from src.scoring_utils import calculate_weighted_total, determine_tier

logger = logging.getLogger("scout.horizon")

FOUNDER_PROFILE_PATH = Path("./config/founder_profile.yaml")
SYSTEM_PROMPT_PATH = Path("./SYSTEM_PROMPT.md")
HORIZON_LENSES_PATH = Path("./config/horizon_lenses.yaml")


class HorizonScanner:
    """
    7-Lens Unbounded Discovery Engine.
    Finds opportunities no predefined source list would ever surface.
    """

    LENS_NAMES = [
        'analogy_transfer', 'friction_mapper', 'convergence_detector',
        'platform_gap', 'regulation_arbitrage', 'dying_industry',
        'founder_inversion'
    ]

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.client = Anthropic(
            api_key=config.get('claude', {}).get('api_key')
            or os.environ.get('ANTHROPIC_API_KEY')
        )
        self._founder_profile = self._load_file(FOUNDER_PROFILE_PATH)
        self._system_prompt = self._load_file(SYSTEM_PROMPT_PATH)
        self._lens_config = self._load_lens_config()
        self._min_founder_fit = config.get('horizon', {}).get('min_founder_fit', 4)

    # ═══════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════

    def daily_scan(self) -> dict:
        """
        Run 3 rotating lenses with Sonnet for fast daily discovery.
        Returns dict with all opportunities found.
        """
        schedule = self._lens_config.get('schedule', {})
        model = schedule.get('daily_model', 'claude-sonnet-4-20250514')
        max_tokens = schedule.get('daily_max_tokens', 4096)
        lens_count = schedule.get('daily_lens_count', 3)

        # Select lenses: rotate through daily-eligible lenses
        eligible = [name for name in self.LENS_NAMES
                    if self._lens_config.get('lenses', {}).get(name, {}).get('daily_eligible', True)]
        day = datetime.utcnow().timetuple().tm_yday
        selected = []
        for i in range(lens_count):
            idx = (day + i) % len(eligible)
            selected.append(eligible[idx])

        logger.info(f"🔭 Horizon daily scan: {', '.join(selected)} (model: {model})")
        return self._run_lenses(selected, model, max_tokens)

    def weekly_deep_scan(self) -> dict:
        """
        Run ALL 7 lenses with Opus for deep weekly discovery.
        """
        schedule = self._lens_config.get('schedule', {})
        model = schedule.get('weekly_model', 'claude-opus-4-20250514')
        max_tokens = schedule.get('weekly_max_tokens', 8192)

        enabled = [name for name in self.LENS_NAMES
                   if self._lens_config.get('lenses', {}).get(name, {}).get('enabled', True)]

        logger.info(f"🔭 Horizon deep scan: ALL {len(enabled)} lenses (model: {model})")
        return self._run_lenses(enabled, model, max_tokens)

    # ═══════════════════════════════════════════════════════════
    # LENS ORCHESTRATOR
    # ═══════════════════════════════════════════════════════════

    def _run_lenses(self, lens_names: list, model: str, max_tokens: int) -> dict:
        """Run multiple lenses and aggregate results."""
        known_titles = self._get_known_titles()
        known_sectors = self.kb.get_known_sectors()
        pending_frontiers = self.kb.get_pending_frontiers(limit=5)

        all_opportunities = []
        all_frontiers = []
        lens_results = {}

        lens_dispatch = {
            'analogy_transfer': self._lens_analogy_transfer,
            'friction_mapper': self._lens_friction_mapper,
            'convergence_detector': self._lens_convergence_detector,
            'platform_gap': self._lens_platform_gap,
            'regulation_arbitrage': self._lens_regulation_arbitrage,
            'dying_industry': self._lens_dying_industry,
            'founder_inversion': self._lens_founder_inversion,
        }

        for lens_name in lens_names:
            lens_fn = lens_dispatch.get(lens_name)
            if not lens_fn:
                continue

            lens_cfg = self._lens_config.get('lenses', {}).get(lens_name, {})
            max_loops = lens_cfg.get('max_loops', 15)

            start_time = time.time()
            logger.info(f"🔭 Running lens: {lens_cfg.get('name', lens_name)}")

            try:
                result = lens_fn(
                    model=model,
                    max_tokens=max_tokens,
                    max_loops=max_loops,
                    known_titles=known_titles,
                    known_sectors=known_sectors,
                    pending_frontiers=pending_frontiers
                )

                opportunities = result.get('opportunities', [])
                new_frontiers = result.get('new_frontiers', [])
                duration = time.time() - start_time

                # Store opportunities
                stored = self._store_results(opportunities, f"horizon_{lens_name}")

                # Process new frontiers (self-expanding)
                saved_frontiers = self._process_new_frontiers(new_frontiers, lens_name)
                all_frontiers.extend(saved_frontiers)

                # Update any explored pending frontiers
                self._update_frontier_results(pending_frontiers, stored)

                # Track performance
                scores = [o.get('weighted_total', 0) for o in stored]
                fire_count = len([o for o in stored if o.get('tier') == 'FIRE'])
                high_count = len([o for o in stored if o.get('tier') == 'HIGH'])

                self.kb.log_strategy_performance(
                    engine='horizon',
                    strategy_name=lens_name,
                    opportunities_found=len(stored),
                    avg_score=round(sum(scores) / len(scores), 1) if scores else 0,
                    best_score=max(scores) if scores else 0,
                    fire_count=fire_count,
                    high_count=high_count,
                    duration_seconds=round(duration, 1)
                )

                all_opportunities.extend(stored)
                lens_results[lens_name] = {
                    'found': len(stored),
                    'fire': fire_count,
                    'high': high_count,
                    'frontiers_discovered': len(saved_frontiers),
                    'duration': round(duration, 1)
                }

                logger.info(
                    f"🔭 {lens_cfg.get('name', lens_name)}: "
                    f"{len(stored)} opps ({fire_count} FIRE, {high_count} HIGH), "
                    f"{len(saved_frontiers)} new frontiers, {duration:.0f}s"
                )

            except Exception as e:
                logger.error(f"🔭 Lens {lens_name} failed: {e}", exc_info=True)
                lens_results[lens_name] = {'error': str(e)}

        return {
            'opportunities': all_opportunities,
            'lens_results': lens_results,
            'new_frontiers': all_frontiers,
            'total_found': len(all_opportunities)
        }

    # ═══════════════════════════════════════════════════════════
    # LENS 1: ANALOGY TRANSFER
    # ═══════════════════════════════════════════════════════════

    def _lens_analogy_transfer(self, **kwargs) -> dict:
        """What succeeded in country X that doesn't exist in UK/Turkey/UAE?"""
        known_sectors = kwargs.get('known_sectors', [])
        known_titles = kwargs.get('known_titles', [])

        # Rotate through different source countries
        countries = ['Japan', 'South Korea', 'Brazil', 'India', 'Sweden',
                     'Germany', 'Indonesia', 'Nigeria', 'Israel', 'Australia']
        day = datetime.utcnow().timetuple().tm_yday
        focus_countries = [countries[i % len(countries)] for i in range(day, day + 3)]

        prompt = f"""You are the ANALOGY TRANSFER lens of OpportunityScout's Horizon Scanner.

YOUR MENTAL MODEL: The best business ideas are often copies of what works elsewhere.
Yemeksepeti copied GrubHub for Turkey. Trendyol copied Farfetch. Glovo copied DoorDash for Southern Europe.
Your job is to find what's WORKING in other countries that has NO equivalent in UK, Turkey, or UAE.

TODAY'S FOCUS COUNTRIES: {', '.join(focus_countries)}
(But you can look at ANY country — these are just starting points.)

RESEARCH PROCESS:
1. Search for the fastest-growing startups and business models in {focus_countries[0]}:
   - "top startups {focus_countries[0]} 2025 2026"
   - "fastest growing companies {focus_countries[0]} funding"
   - "YC alumni from {focus_countries[0]}"

2. For EACH interesting company, check:
   - "[company name] UK equivalent alternative"
   - "[company name] Turkey equivalent"
   - Is there a gap? Is the market big enough?

3. Search for the fastest-growing startups in {focus_countries[1]} and {focus_countries[2]}.

4. ALSO search broadly: "business models that don't exist in UK", "startup ideas from Asia for Europe"

NOVELTY REQUIREMENT: At least 50% of your results MUST be in sectors NOT in this list:
{', '.join(known_sectors[:20]) if known_sectors else 'No known sectors yet'}

OPERATOR CONTEXT (brief — do NOT limit yourself to these):
- Factory in Turkey (20,000m2, CNC, coatings)
- IT infrastructure expertise (20yr)
- AI/Python development
- Companies in UK, Turkey, UAE, USA

ALREADY KNOWN (avoid repeats):
{chr(10).join(f'- {t}' for t in known_titles[:15])}

For EACH opportunity, include "discovery_path" explaining: source country → original company → local gap → opportunity.
Include "action_by" date (YYYY-MM-DD or null) for time-sensitive opportunities.
Score each on 10 dimensions. Include founder_fit even if it's low — let the scoring decide.

Also output a "new_frontiers" array — any genuinely NEW sectors, buyer personas, or technologies
you discovered that OpportunityScout has never explored before.

CRITICAL: Your ENTIRE response must be ONLY a valid JSON object. No text before or after.
Format: {{"opportunities": [...], "signals": [...], "new_frontiers": [{{"frontier_name": "...", "frontier_type": "sector|buyer_persona|technology|regulation", "search_queries": ["query1", "query2"]}}]}}"""

        return self._execute_search(prompt, kwargs['model'], kwargs['max_tokens'], kwargs['max_loops'])

    # ═══════════════════════════════════════════════════════════
    # LENS 2: FRICTION MAPPER
    # ═══════════════════════════════════════════════════════════

    def _lens_friction_mapper(self, **kwargs) -> dict:
        """Where do people waste the most time/money on broken processes?"""
        known_sectors = kwargs.get('known_sectors', [])
        known_titles = kwargs.get('known_titles', [])

        # Rotate through different friction angles
        angles = [
            '"most hated business process" OR "worst business software"',
            '"most expensive manual task" OR "still using spreadsheets"',
            '"industries resistant to technology" OR "still using fax"',
            '"biggest time waste at work" OR "most inefficient process"',
            '"customers complaining about" OR "worst customer experience"',
        ]
        day = datetime.utcnow().timetuple().tm_yday
        focus_angle = angles[day % len(angles)]

        prompt = f"""You are the FRICTION MAPPER lens of OpportunityScout's Horizon Scanner.

YOUR MENTAL MODEL: Every billion-dollar company was built by removing friction.
Uber removed taxi-hailing friction. Stripe removed payment friction. Slack removed email friction.
Friction = money. The bigger the friction, the bigger the opportunity.

YOUR RESEARCH PROCESS:
1. Search for: {focus_angle}
2. Search for: "industries that still use paper", "manual processes costing businesses millions"
3. Search for: "startup solving [friction]" — to see who's already working on it and where gaps remain
4. Search for: "complaints about [industry] process" across Reddit, forums, Trustpilot
5. For EACH friction you find, estimate:
   - How much does this friction COST per year? (time × hourly rate × frequency)
   - How many businesses/people experience it?
   - What would a 10x better solution look like?
   - Could AI/automation solve this?

DO NOT limit yourself to any sector. Look at healthcare, logistics, education, government,
agriculture, legal, real estate, HR, finance, manufacturing, retail — ANYTHING.

NOVELTY REQUIREMENT: At least 50% of your results MUST be in sectors NOT in this list:
{', '.join(known_sectors[:20]) if known_sectors else 'No known sectors yet'}

OPERATOR CONTEXT (brief — for scoring, not filtering):
- Factory in Turkey (20,000m2, CNC, coatings)
- IT infrastructure expertise (20yr)
- AI/Python development
- Companies in UK, Turkey, UAE, USA

ALREADY KNOWN (avoid repeats):
{chr(10).join(f'- {t}' for t in known_titles[:15])}

For EACH opportunity, include "discovery_path" explaining: friction → size → current solutions → gap → opportunity.
Include "action_by" date (YYYY-MM-DD or null) for time-sensitive opportunities.
Score each on 10 dimensions. Include founder_fit even if it's low.

Also output "new_frontiers" — any genuinely NEW sectors or friction areas you discovered.

CRITICAL: Your ENTIRE response must be ONLY a valid JSON object. No text before or after.
Format: {{"opportunities": [...], "signals": [...], "new_frontiers": [...]}}"""

        return self._execute_search(prompt, kwargs['model'], kwargs['max_tokens'], kwargs['max_loops'])

    # ═══════════════════════════════════════════════════════════
    # LENS 3: CONVERGENCE DETECTOR
    # ═══════════════════════════════════════════════════════════

    def _lens_convergence_detector(self, **kwargs) -> dict:
        """Where are 2+ macro trends colliding to create new categories?"""
        known_titles = kwargs.get('known_titles', [])
        known_sectors = kwargs.get('known_sectors', [])

        # Macro trends pool — deliberately broad
        trends_pool = [
            "aging population globally",
            "remote/hybrid work permanence",
            "AI agents replacing human tasks",
            "climate regulation tightening (EU CBAM, UK ETS)",
            "supply chain reshoring to Turkey/Eastern Europe",
            "creator economy explosion",
            "loneliness epidemic",
            "electric vehicle transition",
            "space commercialization",
            "genomics/personalized medicine",
            "water scarcity",
            "housing affordability crisis",
            "gig economy regulation",
            "quantum computing approaching",
            "biodiversity credits / nature markets",
        ]
        day = datetime.utcnow().timetuple().tm_yday
        # Pick 5 trends to intersect
        selected = [trends_pool[(day + i) % len(trends_pool)] for i in range(5)]

        prompt = f"""You are the CONVERGENCE DETECTOR lens of OpportunityScout's Horizon Scanner.

YOUR MENTAL MODEL: The biggest businesses are born where 2+ macro trends COLLIDE.
Telemedicine = aging population + internet infrastructure.
PropTech = real estate + fintech + mobile.
Climate fintech = ESG regulations + banking APIs.
These intersections create ENTIRELY NEW categories that didn't exist 5 years ago.

TODAY'S TRENDS TO INTERSECT:
{chr(10).join(f'  {i+1}. {t}' for i, t in enumerate(selected))}

YOUR RESEARCH PROCESS:
1. For EACH pair of trends above, search: "intersection of [trend A] and [trend B] business opportunity"
2. Search: "new business category 2025 2026" "emerging market created by"
3. Search: "what business does [trend] + [trend] create?"
4. For each intersection that looks promising:
   - Is anyone already building here? How funded are they?
   - What's the market size potential?
   - Is there a UK/Turkey/UAE angle?

You should search for at least 6 trend-pair intersections. Think CREATIVELY:
- What does "aging + AI" create? (AI elderly companions, automated care, silver tech)
- What does "remote work + loneliness" create? (co-living, virtual offices, connection platforms)
- What does "climate regulation + manufacturing" create? (carbon accounting, green materials)

NOVELTY REQUIREMENT: At least 50% of results MUST be outside known sectors:
{', '.join(known_sectors[:20]) if known_sectors else 'No known sectors yet'}

OPERATOR CONTEXT: Factory(TR), IT infra(20yr), AI/Python, UK+TR+UAE+USA entities.

ALREADY KNOWN (avoid):
{chr(10).join(f'- {t}' for t in known_titles[:15])}

Each opportunity MUST have "discovery_path": trend A + trend B → intersection → opportunity.
Include "action_by" date (YYYY-MM-DD or null) for time-sensitive opportunities.
Score each 10 dimensions. Include founder_fit even if low.
Output "new_frontiers" for any new sectors discovered.

CRITICAL: Your ENTIRE response must be ONLY a valid JSON object. No text before or after.
Format: {{"opportunities": [...], "signals": [...], "new_frontiers": [...]}}"""

        return self._execute_search(prompt, kwargs['model'], kwargs['max_tokens'], kwargs['max_loops'])

    # ═══════════════════════════════════════════════════════════
    # LENS 4: PLATFORM GAP SCANNER
    # ═══════════════════════════════════════════════════════════

    def _lens_platform_gap(self, **kwargs) -> dict:
        """What 2-sided marketplaces are missing?"""
        known_titles = kwargs.get('known_titles', [])
        known_sectors = kwargs.get('known_sectors', [])

        prompt = f"""You are the PLATFORM GAP lens of OpportunityScout's Horizon Scanner.

YOUR MENTAL MODEL: The most valuable companies are PLATFORMS that connect buyers and sellers.
Amazon (buyer ↔ seller), Uber (rider ↔ driver), Airbnb (guest ↔ host), Upwork (client ↔ freelancer).
There are still HUNDREDS of industries where buyers and sellers find each other through
phone calls, brokers, trade shows, outdated directories, or word-of-mouth. Each is a potential platform.

YOUR RESEARCH PROCESS:
1. Search: "industries still using brokers" "marketplace opportunity"
2. Search: "B2B marketplace startups 2025 2026" — what's been funded? What verticals?
3. Search: "fragmented industry needs marketplace" "too many small suppliers"
4. Search: "trade show directory outdated" "[industry] needs digital platform"
5. For EACH gap you find:
   - Who are the buyers? How many? How much do they spend?
   - Who are the sellers? How fragmented? How do they currently get customers?
   - What would a marketplace look like? (transaction model, SaaS fee, lead gen?)
   - Is there cross-border potential (Turkish sellers → UK/EU buyers)?

Think BROADLY — not just tech:
- Industrial parts sourcing
- Specialty food ingredients
- Architect ↔ material supplier
- Landlord ↔ property maintenance
- School ↔ educational supplier
- Hospital ↔ medical device supplier
- Restaurant ↔ specialty food producer

NOVELTY REQUIREMENT: At least 50% of results MUST be outside known sectors:
{', '.join(known_sectors[:20]) if known_sectors else 'None yet'}

OPERATOR CONTEXT: Factory(TR), IT infra(20yr), AI/Python, UK+TR+UAE+USA entities.
(The 4-country presence makes marketplace building especially credible for cross-border.)

ALREADY KNOWN (avoid):
{chr(10).join(f'- {t}' for t in known_titles[:15])}

Each opportunity MUST have "discovery_path": fragmented industry → buyer pain → seller pain → platform model.
Include "action_by" date (YYYY-MM-DD or null).
Score each 10 dimensions. Include founder_fit even if low.
Output "new_frontiers" for new sectors discovered.

CRITICAL: Your ENTIRE response must be ONLY a valid JSON object. No text before or after.
Format: {{"opportunities": [...], "signals": [...], "new_frontiers": [...]}}"""

        return self._execute_search(prompt, kwargs['model'], kwargs['max_tokens'], kwargs['max_loops'])

    # ═══════════════════════════════════════════════════════════
    # LENS 5: REGULATION ARBITRAGE
    # ═══════════════════════════════════════════════════════════

    def _lens_regulation_arbitrage(self, **kwargs) -> dict:
        """What new rules just created captive demand?"""
        known_titles = kwargs.get('known_titles', [])
        known_sectors = kwargs.get('known_sectors', [])

        prompt = f"""You are the REGULATION ARBITRAGE lens of OpportunityScout's Horizon Scanner.

YOUR MENTAL MODEL: New regulations CREATE billion-dollar markets overnight.
GDPR created a $3B compliance industry. SOX created the audit-tech industry.
PSD2 created open banking. REACH created chemicals compliance consulting.
Every new regulation means: someone now MUST buy something they didn't before.

YOUR RESEARCH PROCESS:
1. Search: "new regulations 2025 2026" "upcoming compliance deadline"
2. Search: "EU new directive 2026" "UK new law 2026" "UAE new regulation"
3. Search: "Turkey new regulation export" "US new compliance requirement"
4. Search: "industries affected by new regulation" "compliance cost estimate"
5. For EACH regulation found:
   - WHO must comply? (how many businesses?)
   - WHAT must they buy/do/change?
   - WHEN is the deadline?
   - What solutions exist? Are they good or terrible?
   - What's the gap?

Search BROADLY — not just UK Building Safety Act:
- Environmental (CBAM, ETS, plastic tax, EPR)
- Financial (Basel IV, DORA, AML 6th directive)
- Technology (AI Act, NIS2, Cyber Resilience Act)
- Employment (pay transparency, right to disconnect)
- Healthcare (MDR, IVDR medical devices)
- Trade (customs, CPTPP, sanctions compliance)
- Real estate (EPC, building safety, accessibility)

NOVELTY REQUIREMENT: At least 50% of results MUST be outside known sectors:
{', '.join(known_sectors[:20]) if known_sectors else 'None yet'}

OPERATOR CONTEXT: Factory(TR), IT infra(20yr), AI/Python, UK+TR+UAE+USA entities.

ALREADY KNOWN (avoid):
{chr(10).join(f'- {t}' for t in known_titles[:15])}

Each opportunity MUST have "discovery_path": regulation → who must comply → what they must buy → gap → opportunity.
Include "action_by" date (YYYY-MM-DD — the compliance deadline!) for EVERY regulation-driven opportunity.
Score each 10 dimensions. Include founder_fit even if low.
Output "new_frontiers" for new sectors discovered.

CRITICAL: Your ENTIRE response must be ONLY a valid JSON object. No text before or after.
Format: {{"opportunities": [...], "signals": [...], "new_frontiers": [...]}}"""

        return self._execute_search(prompt, kwargs['model'], kwargs['max_tokens'], kwargs['max_loops'])

    # ═══════════════════════════════════════════════════════════
    # LENS 6: DYING INDUSTRY AUTOPSY
    # ═══════════════════════════════════════════════════════════

    def _lens_dying_industry(self, **kwargs) -> dict:
        """What industries are declining, and what replaces them?"""
        known_titles = kwargs.get('known_titles', [])
        known_sectors = kwargs.get('known_sectors', [])

        prompt = f"""You are the DYING INDUSTRY AUTOPSY lens of OpportunityScout's Horizon Scanner.

YOUR MENTAL MODEL: Every dying industry leaves behind UNMET NEEDS that create new businesses.
Video rental died → Netflix/streaming.
Retail stores declined → Shopify/e-commerce.
On-premise servers died → AWS/cloud.
Taxi dispatching died → Uber.
The NEED doesn't die — only the delivery method changes. Find the next transitions.

YOUR RESEARCH PROCESS:
1. Search: "industries in decline 2025 2026" "dying businesses"
2. Search: "companies going bankrupt UK Europe" "sector losing workers"
3. Search: "what replaces [dying industry]" "modern alternative to"
4. Search: "industries disrupted by AI" "jobs being automated"
5. For EACH dying/declining industry:
   - WHAT NEED did it serve? (That need still exists!)
   - WHO served those customers? (They're now underserved)
   - WHAT MODERN APPROACH replaces the old way?
   - Is anyone building the replacement? How far along?
   - Could the operator build this replacement?

Think about:
- Traditional IT resellers → what replaces them?
- Print media → what replaces local business information?
- Physical trade shows → what replaces B2B discovery?
- Traditional manufacturing agents → what replaces them?
- Manual accounting firms → what replaces them?
- In-person training → what replaces industry certifications?

NOVELTY REQUIREMENT: At least 50% of results MUST be outside known sectors:
{', '.join(known_sectors[:20]) if known_sectors else 'None yet'}

OPERATOR CONTEXT: Factory(TR), IT infra(20yr), AI/Python, UK+TR+UAE+USA entities.

ALREADY KNOWN (avoid):
{chr(10).join(f'- {t}' for t in known_titles[:15])}

Each opportunity MUST have "discovery_path": dying industry → unmet need → modern replacement → gap → opportunity.
Include "action_by" date (YYYY-MM-DD or null).
Score each 10 dimensions. Include founder_fit even if low.
Output "new_frontiers" for new sectors discovered.

CRITICAL: Your ENTIRE response must be ONLY a valid JSON object. No text before or after.
Format: {{"opportunities": [...], "signals": [...], "new_frontiers": [...]}}"""

        return self._execute_search(prompt, kwargs['model'], kwargs['max_tokens'], kwargs['max_loops'])

    # ═══════════════════════════════════════════════════════════
    # LENS 7: FOUNDER ASSET INVERSION
    # ═══════════════════════════════════════════════════════════

    def _lens_founder_inversion(self, **kwargs) -> dict:
        """What if the founder's assets ARE the product?"""
        known_titles = kwargs.get('known_titles', [])

        prompt = f"""You are the FOUNDER ASSET INVERSION lens of OpportunityScout's Horizon Scanner.

YOUR MENTAL MODEL: Most people ask "what opportunities fit me?" WRONG QUESTION.
The right question: "Who would PAY to access what I already HAVE?"

The operator has RARE assets. Instead of finding opportunities for these assets,
find BUYERS for these assets.

OPERATOR'S ASSETS (treat each as a potential PRODUCT):

ASSET 1 — FACTORY (20,000m2 in Turkey)
- 5-axis CNC, edge banding, coil coating paint line
- Turkish labor cost (~$800/month) vs UK ($3,500/month)
- Search: "who needs contract manufacturing in Turkey?"
- Search: "companies looking for cheaper production in Europe"
- Search: "nearshoring manufacturing Turkey 2026"

ASSET 2 — IT INFRASTRUCTURE EXPERTISE (20 years)
- Cisco, VMware, Palo Alto, VDI, Veeam — deep hands-on
- Search: "companies struggling to find IT infrastructure talent"
- Search: "MSP looking for remote IT expertise"
- Search: "outsourced IT infrastructure management demand"

ASSET 3 — 4-COUNTRY LEGAL STRUCTURE (UK, Turkey, UAE, USA)
- Search: "companies need entity in Turkey for business"
- Search: "UK company needs UAE subsidiary"
- Search: "cross-border compliance consulting demand"

ASSET 4 — AI/AUTOMATION DEVELOPMENT (Python, Claude API, n8n)
- Search: "businesses looking for AI automation"
- Search: "n8n consultants demand" "workflow automation for hire"

ASSET 5 — COATING/CHEMICALS CAPABILITY
- Coil coating line, intumescent knowledge, specialty paints
- Search: "specialty coating contract manufacturing"
- Search: "private label paint manufacturing Turkey"

For EACH asset, find at least 2 SPECIFIC buyers or buyer segments who would pay for access.
Not vague markets — specific company types, procurement patterns, price points.

ALREADY KNOWN (avoid):
{chr(10).join(f'- {t}' for t in known_titles[:15])}

Each opportunity MUST have "discovery_path": asset → buyer need → pricing model → opportunity.
Include "action_by" date (YYYY-MM-DD or null).
Score each 10 dimensions.
Output "new_frontiers" for any new buyer segments or industries you discover.

CRITICAL: Your ENTIRE response must be ONLY a valid JSON object. No text before or after.
Format: {{"opportunities": [...], "signals": [...], "new_frontiers": [...]}}"""

        return self._execute_search(prompt, kwargs['model'], kwargs['max_tokens'], kwargs['max_loops'])

    # ═══════════════════════════════════════════════════════════
    # SEARCH EXECUTION (shared by all lenses)
    # ═══════════════════════════════════════════════════════════

    def _execute_search(self, prompt: str, model: str,
                        max_tokens: int, max_loops: int) -> dict:
        """Execute a multi-turn web search conversation with Claude."""
        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=self._system_prompt,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=messages
            )

            loop_count = 0
            while response.stop_reason == "tool_use" and loop_count < max_loops:
                loop_count += 1
                logger.info(f"   🔍 Search loop {loop_count}")
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Search completed."
                        })

                messages.append({"role": "user", "content": tool_results})

                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=self._system_prompt,
                    tools=[{"type": "web_search_20250305", "name": "web_search"}],
                    messages=messages
                )

            text = self._extract_text(response)
            results = self._parse_json_response(text)

            # Filter by founder fit (but lower threshold than serendipity — we want breadth)
            opps = results.get('opportunities', [])
            filtered = []
            for opp in opps:
                scores = opp.get('scores', {})
                ff = scores.get('founder_fit', {})
                ff_score = ff.get('score', 0) if isinstance(ff, dict) else (
                    ff if isinstance(ff, (int, float)) else 0
                )
                if ff_score >= self._min_founder_fit:
                    filtered.append(opp)

            return {
                "opportunities": filtered,
                "signals": results.get('signals', []),
                "new_frontiers": results.get('new_frontiers', []),
                "search_loops": loop_count
            }

        except Exception as e:
            logger.error(f"Horizon search execution failed: {e}", exc_info=True)
            return {"opportunities": [], "signals": [], "new_frontiers": []}

    # ═══════════════════════════════════════════════════════════
    # SELF-EXPANDING FRONTIER MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def _process_new_frontiers(self, frontiers: list, lens_name: str) -> list:
        """Process and store newly discovered frontiers."""
        max_new = self._lens_config.get('frontiers', {}).get('max_new_per_run', 5)
        saved = []

        for frontier in frontiers[:max_new]:
            if not isinstance(frontier, dict):
                continue
            name = frontier.get('frontier_name', '').strip()
            if not name or len(name) < 3:
                continue

            result = self.kb.save_frontier({
                'frontier_name': name,
                'frontier_type': frontier.get('frontier_type', 'sector'),
                'discovered_by_lens': lens_name,
                'search_queries': frontier.get('search_queries', [])
            })
            if result > 0:
                saved.append(name)
                logger.info(f"   🌱 New frontier discovered: {name}")

        return saved

    def _update_frontier_results(self, frontiers: list, stored_opps: list):
        """Update frontier status based on exploration results."""
        min_score = self._lens_config.get('frontiers', {}).get('min_score_for_productive', 100)
        max_attempts = self._lens_config.get('frontiers', {}).get('max_explore_attempts', 3)

        for frontier in frontiers:
            fid = frontier.get('id')
            if not fid:
                continue

            # Check if any stored opp relates to this frontier
            frontier_name = frontier.get('frontier_name', '').lower()
            related = [o for o in stored_opps
                       if frontier_name in (o.get('sector', '') or '').lower()
                       or frontier_name in ' '.join(o.get('tags', [])).lower()]

            best = max((o.get('weighted_total', 0) for o in related), default=0)

            if best >= min_score:
                status = 'productive'
            elif frontier.get('times_explored', 0) >= max_attempts:
                status = 'exhausted'
            else:
                status = 'explored'

            self.kb.update_frontier_status(fid, status, len(related), best)

    # ═══════════════════════════════════════════════════════════
    # STORAGE
    # ═══════════════════════════════════════════════════════════

    def _store_results(self, opportunities: list, source_type: str) -> list:
        """Store horizon findings in the knowledge base."""
        stored = []
        for opp in opportunities:
            opp['source'] = source_type
            if 'horizon' not in opp.get('tags', []):
                opp.setdefault('tags', []).append('horizon')

            # Recalculate score and tier
            opp['weighted_total'] = calculate_weighted_total(opp.get('scores', {}))
            opp['tier'] = determine_tier(opp['weighted_total'])

            if not self.kb.is_duplicate(opp.get('title', ''), source_type,
                                        sector=opp.get('sector', ''),
                                        tags=opp.get('tags', [])):
                self.kb.save_opportunity(opp)
                stored.append(opp)

        return stored

    # ═══════════════════════════════════════════════════════════
    # CONTEXT & HELPERS
    # ═══════════════════════════════════════════════════════════

    def _get_known_titles(self, limit: int = 50) -> list:
        """Get titles of known opportunities to avoid repetition."""
        opps = self.kb.get_top_opportunities(limit=limit)
        return [o.get('title', '') for o in opps if o.get('title')]

    @staticmethod
    def _load_file(path: Path) -> str:
        """Load a text/yaml file as string."""
        try:
            return path.read_text()
        except FileNotFoundError:
            return ""

    def _load_lens_config(self) -> dict:
        """Load horizon lens configuration."""
        try:
            with open(HORIZON_LENSES_PATH) as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}

    # ═══════════════════════════════════════════════════════════
    # JSON PARSING (5-strategy robust parser)
    # ═══════════════════════════════════════════════════════════

    def _parse_json_response(self, text: str) -> dict:
        """5-strategy JSON parser with truncated repair."""
        if not text:
            return {"opportunities": [], "signals": [], "new_frontiers": []}

        # Strategy 1: Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract from code fence
        fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find first { to last }
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass

        # Strategy 4: Repair truncated JSON
        if first_brace != -1:
            try:
                repaired = self._repair_truncated_json(text[first_brace:])
                return json.loads(repaired)
            except (json.JSONDecodeError, Exception):
                pass

        # Strategy 5: Greedy regex for opportunities array
        opp_match = re.search(r'"opportunities"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if opp_match:
            try:
                opps = json.loads('[' + opp_match.group(1) + ']')
                return {"opportunities": opps, "signals": [], "new_frontiers": []}
            except json.JSONDecodeError:
                pass

        logger.warning("All 5 JSON parse strategies failed for horizon response")
        return {"opportunities": [], "signals": [], "new_frontiers": []}

    @staticmethod
    def _repair_truncated_json(text: str) -> str:
        """Repair truncated JSON by closing open brackets/braces."""
        stack = []
        in_string = False
        escape_next = False
        last_safe = 0

        for i, ch in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in '{[':
                stack.append('}' if ch == '{' else ']')
            elif ch in '}]':
                if stack and stack[-1] == ch:
                    stack.pop()
                    last_safe = i

        if not stack:
            return text

        # Find safe truncation point
        safe_text = text[:last_safe + 1]
        # Close remaining brackets
        closing = ''.join(reversed(stack))
        return safe_text + closing

    @staticmethod
    def _extract_text(response) -> str:
        """Extract text content from Claude API response."""
        parts = []
        for block in response.content:
            if hasattr(block, 'text'):
                parts.append(block.text)
        return '\n'.join(parts)
