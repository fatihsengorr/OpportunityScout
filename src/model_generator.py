"""
OpportunityScout — Business Model Generator v2 (3-Lens Creative Engine)

The CREATIVE brain of the scout. INVENTS new business models by running
3 independent creative lenses, each with a fundamentally different approach:

  Lens 1: CROSS-POLLINATION SYNTHESIZER — Connects dots from accumulated intelligence
  Lens 2: FIRST PRINCIPLES INVENTOR — Raw capabilities only, no accumulated data
  Lens 3: INVERSION ENGINE — Starts from buyer pain, works backward to solutions

Each lens runs as a separate Opus conversation. Results are merged, scored,
validated, and the best models are presented regardless of which lens produced them.

Performance is tracked per lens via the strategy_performance table.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from src.scoring_utils import calculate_weighted_total, determine_tier
from pathlib import Path
from .llm_router import LLMRouter

logger = logging.getLogger("scout.generator")

# Load founder profile for capability matching
FOUNDER_PROFILE_PATH = Path("./config/founder_profile.yaml")
SYSTEM_PROMPT_PATH = Path("./SYSTEM_PROMPT.md")


class BusinessModelGenerator:
    """
    Synthesizes accumulated intelligence into novel business model proposals.
    This is the module that answers: "What business should I build that
    nobody else can see?"
    """

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.llm = LLMRouter(config)
        self.model = self.llm.get_model('weekly')
        self.max_tokens = 8192
        self._founder_profile = self._load_founder_profile()
        self._system_prompt = self._load_system_prompt()

    LENS_NAMES = ['cross_pollination', 'first_principles', 'inversion']

    def generate(self, focus_area: str = None, count: int = 3) -> dict:
        """
        Generate novel business models using 3 creative lenses.

        Each lens runs independently, produces models, then all are merged,
        scored, validated, and the best are returned.

        Args:
            focus_area: Optional focus constraint (e.g., "scan-to-bim").
            count: Total number of business models to return (default 3).

        Returns:
            dict with "models" list + lens performance data.
        """
        logger.info(f"💡 3-Lens Generator: {count} models"
                    f"{f' (focus: {focus_area})' if focus_area else ''}...")

        # Phase 1: Gather intelligence + build DNA exclusion list
        context = self._build_intelligence_context(focus_area)
        dna_exclusions = self._build_dna_exclusions()

        # Phase 2: Run all 3 lenses
        all_raw_models = []
        lens_results = {}

        # Distribute count across lenses (at least 1 per lens)
        per_lens = max(1, count // 3)
        lens_counts = {
            'cross_pollination': per_lens,
            'first_principles': per_lens,
            'inversion': per_lens
        }
        # Give remainder to first_principles (most novel)
        remainder = count - sum(lens_counts.values())
        if remainder > 0:
            lens_counts['first_principles'] += remainder

        lenses = [
            ('cross_pollination', self._lens_cross_pollination),
            ('first_principles', self._lens_first_principles),
            ('inversion', self._lens_inversion),
        ]

        for lens_name, lens_fn in lenses:
            start_time = time.time()
            logger.info(f"💡 Running lens: {lens_name} (target: {lens_counts[lens_name]} models)")

            try:
                raw_models = lens_fn(
                    context=context,
                    focus_area=focus_area,
                    count=lens_counts[lens_name],
                    dna_exclusions=dna_exclusions
                )

                duration = time.time() - start_time
                lens_results[lens_name] = {
                    'raw_count': len(raw_models),
                    'duration': round(duration, 1)
                }

                # Tag each model with its lens origin
                for m in raw_models:
                    m['_lens'] = lens_name

                all_raw_models.extend(raw_models)
                logger.info(f"💡 {lens_name}: produced {len(raw_models)} raw models in {duration:.0f}s")

            except Exception as e:
                logger.error(f"💡 Lens {lens_name} failed: {e}")
                lens_results[lens_name] = {'error': str(e)}

        # Phase 3: Score all models
        scored_models = []
        for model in all_raw_models:
            scored = self._score_generated_model(model)
            scored_models.append(scored)

        # Phase 4: Select top N, validate
        top_models = sorted(scored_models,
                           key=lambda m: m.get('weighted_total', 0),
                           reverse=True)[:count]

        validated_models = []
        for model in top_models:
            validated = self._web_validate_model(model)
            validated_models.append(validated)

        # Phase 5: Store + track performance per lens
        for model in validated_models:
            self._store_model(model)

        # Log strategy performance per lens
        for lens_name in self.LENS_NAMES:
            lens_models = [m for m in validated_models
                          if m.get('generated_model', {}).get('_lens') == lens_name
                          or m.get('_lens') == lens_name]
            scores = [m.get('weighted_total', 0) for m in lens_models]
            fire_count = len([m for m in lens_models if m.get('tier') == 'FIRE'])
            high_count = len([m for m in lens_models if m.get('tier') == 'HIGH'])

            self.kb.log_strategy_performance(
                engine='generator',
                strategy_name=lens_name,
                opportunities_found=len(lens_models),
                avg_score=round(sum(scores) / len(scores), 1) if scores else 0,
                best_score=max(scores) if scores else 0,
                fire_count=fire_count,
                high_count=high_count,
                duration_seconds=lens_results.get(lens_name, {}).get('duration', 0)
            )

        result = {
            "models": validated_models,
            "generation_context": {
                "signals_analyzed": context.get('signal_count', 0),
                "trends_analyzed": context.get('trend_count', 0),
                "blind_spots_found": context.get('blind_spot_count', 0),
                "focus_area": focus_area,
                "lenses_used": list(lens_results.keys()),
                "lens_results": lens_results,
                "timestamp": datetime.utcnow().isoformat()
            }
        }

        logger.info(f"💡 3-Lens Generator complete: {len(validated_models)} models")
        for ln, lr in lens_results.items():
            if 'error' not in lr:
                logger.info(f"   {ln}: {lr.get('raw_count', 0)} raw models")
        return result

    # ─── DNA-Level Deduplication ────────────────────────────

    def _build_dna_exclusions(self) -> list:
        """
        Build 'business model DNA' patterns from last 50 generated models.
        DNA = sector + buyer + mechanism + capability_used
        Used to block conceptual variants, not just title duplicates.
        """
        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT title, sector, customer_json, business_model_json,
                       founder_edge, tags_json
                FROM generated_models
                ORDER BY created_at DESC LIMIT 50
            """)
            dna_patterns = []
            for row in cursor.fetchall():
                customer = json.loads(row[2] or '{}')
                biz_model = json.loads(row[3] or '{}')
                tags = json.loads(row[5] or '[]')
                dna = {
                    'title': row[0],
                    'sector': row[1] or '',
                    'buyer': customer.get('who', ''),
                    'revenue_type': biz_model.get('revenue_type', ''),
                    'founder_edge_summary': (row[4] or '')[:100],
                    'tags': tags[:5]
                }
                dna_patterns.append(dna)
            return dna_patterns
        except Exception:
            return []

    # ═══════════════════════════════════════════════════════════
    # LENS 1: CROSS-POLLINATION SYNTHESIZER
    # ═══════════════════════════════════════════════════════════

    def _lens_cross_pollination(self, context: dict, focus_area: str = None,
                                 count: int = 1, dna_exclusions: list = None) -> list:
        """
        Connect dots from accumulated intelligence to invent businesses.
        This is the improved version of the original generator approach.
        """
        context_text = self._format_context_for_prompt(context)
        dna_text = self._format_dna_exclusions(dna_exclusions)

        previous_models = context.get('previous_models', [])
        avoid_text = ""
        if previous_models:
            titles = [m['title'] for m in previous_models]
            avoid_text = (
                f"\nAVOID REPETITION (titles already generated):\n"
                f"{chr(10).join(f'- {t}' for t in titles)}\n"
            )

        focus_instruction = ""
        if focus_area:
            focus_instruction = f"\nFOCUS CONSTRAINT: Generate models related to: {focus_area}\n"

        prompt = f"""You are the Cross-Pollination Synthesizer lens of OpportunityScout's Business Model Generator.

YOUR APPROACH: Connect dots between accumulated signals, trends, and gaps to invent businesses nobody else can see. Your unique advantage is having access to weeks of accumulated market intelligence — USE IT.

{focus_instruction}

OPERATOR PROFILE:
{self._founder_profile}

ACCUMULATED INTELLIGENCE:
{context_text}

{avoid_text}

{dna_text}

MANDATORY DIVERSITY: AT MOST 1 model can be from Construction/BIM. Rest MUST come from different sectors.

Generate exactly {count} business model(s). Each must trace back to specific signals or trends in the accumulated intelligence.

{self._get_model_json_template()}

THINK LATERALLY: What connections between different signals/trends create a business that neither signal alone suggests?"""

        return self._call_opus_for_generation_raw(prompt)

    # ═══════════════════════════════════════════════════════════
    # LENS 2: FIRST PRINCIPLES INVENTOR
    # ═══════════════════════════════════════════════════════════

    def _lens_first_principles(self, context: dict = None, focus_area: str = None,
                                count: int = 1, dna_exclusions: list = None) -> list:
        """
        Start from RAW capabilities only. No signals, no trends, no
        existing opportunities. Breaks out of the echo chamber.
        """
        dna_text = self._format_dna_exclusions(dna_exclusions)

        focus_instruction = ""
        if focus_area:
            focus_instruction = f"\nFOCUS CONSTRAINT: Generate models related to: {focus_area}\n"

        prompt = f"""You are the First Principles Inventor lens of OpportunityScout's Business Model Generator.

YOUR APPROACH: Forget everything you know about this founder's current business. Start from ZERO. You have ONLY these raw capabilities — imagine you just woke up with these skills and need to build a profitable business from scratch.

{focus_instruction}

RAW CAPABILITIES (this is ALL you know — no market data, no trends, no existing business):

CAPABILITY 1 — PHYSICAL MANUFACTURING:
- 20,000 m² factory with 5-axis CNC machines, edge banding, coating systems
- Coil coating paint line (specialty paints, intumescent coatings, industrial finishes)
- Located in Turkey (low cost production)

CAPABILITY 2 — IT INFRASTRUCTURE (20 years deep):
- Cisco networking (switching, routing, wireless)
- VMware ESXi virtualization
- Horizon VDI (virtual desktop infrastructure)
- Veeam Backup and disaster recovery
- Palo Alto firewalls and security
- VoIP telephony systems
- Network architecture and security design

CAPABILITY 3 — SOFTWARE & AI:
- Python development
- n8n workflow automation
- Claude API / LLM integration
- Terraform / Infrastructure as Code
- AWS cloud services
- Docker containerization
- API development

CAPABILITY 4 — CROSS-BORDER OPERATIONS:
- Company entities in UK, Turkey, UAE, USA
- Import/export logistics experience
- B2B sales across 4 countries
- Government tender process knowledge

CAPABILITY 5 — CONSTRUCTION DOMAIN:
- Fire door compliance (FD30/FD60)
- UK Building Safety Act expertise
- BIM / Scan-to-BIM
- FF&E procurement
(NOTE: max 1 model from this capability)

DESIGN CONSTRAINTS:
- Each business must generate $10K/month within 90 days
- Use capabilities in ways the founder has NEVER considered
- Target buyers the founder has NEVER sold to
- Would make a VC say "why hasn't anyone done this?"

{dna_text}

Generate exactly {count} business model(s). Be WILDLY creative. The whole point is to escape the echo chamber.

{self._get_model_json_template()}

IMPORTANT: Do NOT just repackage IT consulting or furniture manufacturing. Think about what UNUSUAL combination of these capabilities creates something genuinely new. For example: VDI expertise + factory = remote-operated manufacturing? Palo Alto skills + cross-border = cybersecurity for exporters? n8n + coil coating = automated paint formula optimization?"""

        return self._call_opus_for_generation_raw(prompt)

    # ═══════════════════════════════════════════════════════════
    # LENS 3: INVERSION ENGINE (Problem-First)
    # ═══════════════════════════════════════════════════════════

    def _lens_inversion(self, context: dict = None, focus_area: str = None,
                         count: int = 1, dna_exclusions: list = None) -> list:
        """
        Start from PAIN, not capabilities. Find the biggest unsolved
        problems, then check if the founder can solve them.
        """
        dna_text = self._format_dna_exclusions(dna_exclusions)

        focus_instruction = ""
        if focus_area:
            focus_instruction = f"\nFOCUS: Search for problems specifically in: {focus_area}\n"

        prompt = f"""You are the Inversion Engine lens of OpportunityScout's Business Model Generator.

YOUR APPROACH: Start from PAIN, not capabilities. First find the biggest unsolved problems, THEN check if the operator can solve them. This is the opposite of the usual approach.

{focus_instruction}

STEP 1 — PAIN DISCOVERY (use web search extensively):
Search for the biggest unsolved business problems in 2025-2026:
- "biggest pain points UK SMEs 2025"
- "most complained about business services UK"
- "problems small businesses can't solve"
- "industries with worst customer satisfaction"
- "business owners biggest frustrations reddit"
- "what UK businesses overpay for"

Also search in specific verticals:
- Property management pain points
- Manufacturing SME challenges
- Professional services inefficiencies
- E-commerce operational nightmares
- Healthcare admin waste
- Legal sector tech gaps

STEP 2 — SEVERITY RANKING:
For each pain found, evaluate:
- How many businesses have this problem? (market size)
- How much are they currently paying for bad solutions? (willingness to pay)
- How painful is the status quo? (urgency to switch)
- Is the problem getting WORSE? (market timing)

STEP 3 — CAPABILITY MATCH:
Take the top problems and check: Can ANY combination of these capabilities solve it?

Available capabilities:
1. Factory with CNC + coil coating in Turkey (cheap production)
2. 20yr IT infrastructure expertise (Cisco, VMware, Palo Alto, VDI)
3. Python/AI/n8n/AWS development
4. Companies in UK, Turkey, UAE, USA
5. Construction domain knowledge (BSA, fire doors, BIM)

Be creative about combinations. The best matches use 2+ capabilities together.

STEP 4 — BUSINESS MODEL DESIGN:
For viable matches, design complete business models.

{dna_text}

Generate exactly {count} business model(s). Each MUST start from a real, verified pain point found via web search.

{self._get_model_json_template()}

The best opportunity is where buyer pain is 9/10 but nobody has built a good solution yet."""

        return self._call_opus_for_generation_raw(prompt)

    # ─── Shared Generation Helper ──────────────────────────

    def _call_opus_for_generation_raw(self, prompt: str) -> list:
        """Execute a generation prompt with Opus + web search multi-turn loop."""
        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.llm.create(
                model=self.model,
                max_tokens=self.max_tokens,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=messages
            )

            loop_count = 0
            while response.stop_reason == "tool_use" and loop_count < 25:
                loop_count += 1
                logger.info(f"💡 Generation web search loop {loop_count}")
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
                response = self.llm.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    tools=[{"type": "web_search_20250305", "name": "web_search"}],
                    messages=messages
                )

            logger.info(f"💡 Generation: stop_reason={response.stop_reason}, "
                       f"loops={loop_count}")

            text_content = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text_content += block.text

            if not text_content.strip():
                logger.warning("💡 Generation returned empty text")

            return self._parse_models_response(text_content)

        except Exception as e:
            logger.error(f"Opus generation failed: {e}")
            return []

    def _format_dna_exclusions(self, dna_patterns: list = None) -> str:
        """Format DNA exclusions for the prompt."""
        if not dna_patterns:
            return ""

        lines = ["DO NOT generate models matching these DNA patterns (sector+buyer+mechanism):"]
        for dna in dna_patterns[:20]:
            lines.append(
                f"  - [{dna.get('sector', '?')}] "
                f"buyer={dna.get('buyer', '?')}, "
                f"type={dna.get('revenue_type', '?')}, "
                f"edge={dna.get('founder_edge_summary', '?')}"
            )
        return "\n".join(lines) + "\n"

    def _get_model_json_template(self) -> str:
        """Return the expected JSON output format for models."""
        return """Include "action_by" date (YYYY-MM-DD or null) for time-sensitive opportunities.

Return results in this EXACT JSON structure:

```json
{
  "models": [
    {
      "title": "Specific, memorable name",
      "one_liner": "One sentence that makes an investor lean forward",
      "origin_story": "What signals/thinking led to this idea",
      "problem": "Specific painful problem. Who has it? How do they cope?",
      "solution": "What exactly do we build/offer?",
      "ai_unlock": "What AI capability makes this possible NOW?",
      "customer": {
        "who": "Exact buyer persona",
        "pain_level": "1-10",
        "current_spend": "What they pay for bad alternatives",
        "decision_maker": "Who signs the check?"
      },
      "business_model": {
        "revenue_type": "SaaS|Service|Marketplace|Product|Licensing|Hybrid",
        "pricing": "Specific pricing with tiers",
        "unit_economics": "CAC, LTV, margin estimates",
        "time_to_first_revenue": "Realistic estimate"
      },
      "founder_edge": "Why THIS founder wins when others can't",
      "competitive_landscape": "Who else? Why haven't they?",
      "first_move": "Exact action in next 48 hours",
      "week_1_plan": "Day-by-day first week",
      "kill_criteria": "What proves this wrong?",
      "sector": "Primary sector",
      "geography": "UK|US|TR|UAE|Global",
      "tags": ["tag1", "tag2"],
      "confidence": "HIGH|MEDIUM|LOW",
      "confidence_reasoning": "Why?"
    }
  ]
}
```"""

    # ─── Phase 1: Intelligence Gathering ────────────────────

    def _build_intelligence_context(self, focus_area: str = None) -> dict:
        """
        Pull all relevant accumulated data from the knowledge base
        to feed into the creative synthesis engine.
        """
        context = {}

        # Recent high-scoring opportunities (what's working)
        top_opps = self.kb.get_top_opportunities(limit=20)
        context['top_opportunities'] = [
            {
                'title': o.get('title', ''),
                'one_liner': o.get('one_liner', ''),
                'sector': o.get('sector', ''),
                'score': o.get('weighted_total', 0),
                'tier': o.get('tier', ''),
                'tags': o.get('tags', []),
                'why_now': o.get('why_now', ''),
                'revenue_path': o.get('revenue_path', ''),
            }
            for o in top_opps
        ]

        # Recent signals (what's happening in the market)
        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT type, summary, relevance, potential_opportunities_json, tags_json
                FROM signals
                ORDER BY created_at DESC
                LIMIT 50
            """)
            signals = []
            for row in cursor.fetchall():
                signals.append({
                    'type': row[0],
                    'summary': row[1],
                    'relevance': row[2],
                    'potential_opportunities': json.loads(row[3] or '[]'),
                    'tags': json.loads(row[4] or '[]'),
                })
            context['recent_signals'] = signals
            context['signal_count'] = len(signals)
        except Exception as e:
            logger.warning(f"Failed to load signals: {e}")
            context['recent_signals'] = []
            context['signal_count'] = 0

        # Trending topics (what's rising)
        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT keyword, mention_count, trajectory, sources_json
                FROM tracked_trends
                WHERE mention_count >= 2
                ORDER BY mention_count DESC
                LIMIT 30
            """)
            trends = []
            for row in cursor.fetchall():
                trends.append({
                    'keyword': row[0],
                    'mentions': row[1],
                    'trajectory': row[2],
                    'sources': json.loads(row[3] or '[]'),
                })
            context['rising_trends'] = trends
            context['trend_count'] = len(trends)
        except Exception as e:
            logger.warning(f"Failed to load trends: {e}")
            context['rising_trends'] = []
            context['trend_count'] = 0

        # Cross-pollination insights (dot connections)
        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT insight, novel_angle, opportunity_ids_json
                FROM cross_pollinations
                WHERE acted_on = 0
                ORDER BY created_at DESC
                LIMIT 20
            """)
            cross = []
            for row in cursor.fetchall():
                cross.append({
                    'insight': row[0],
                    'novel_angle': row[1],
                    'related_opps': json.loads(row[2] or '[]'),
                })
            context['cross_pollinations'] = cross
        except Exception as e:
            logger.warning(f"Failed to load cross-pollinations: {e}")
            context['cross_pollinations'] = []

        # Evolution log — blind spots (what we're missing)
        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT description, reasoning
                FROM evolution_log
                WHERE action_type IN ('blind_spot', 'pattern_detected')
                ORDER BY created_at DESC
                LIMIT 15
            """)
            blind_spots = []
            for row in cursor.fetchall():
                blind_spots.append({
                    'description': row[0],
                    'reasoning': row[1] or '',
                })
            context['blind_spots'] = blind_spots
            context['blind_spot_count'] = len(blind_spots)
        except Exception as e:
            logger.warning(f"Failed to load blind spots: {e}")
            context['blind_spots'] = []
            context['blind_spot_count'] = 0

        # Source performance (which sectors produce most signal)
        source_perf = self.kb.get_source_performance(days=30)
        top_sources = sorted(
            source_perf,
            key=lambda s: s.get('total_opportunities', 0),
            reverse=True
        )[:10]
        context['top_performing_sources'] = [
            {'name': s['source_name'], 'opps': s['total_opportunities'],
             'avg_score': round(s.get('mean_score', 0), 1)}
            for s in top_sources
        ]

        # Previously generated models (avoid repetition)
        try:
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                SELECT title, one_liner FROM generated_models
                ORDER BY created_at DESC LIMIT 20
            """)
            previous = [{'title': r[0], 'one_liner': r[1]}
                       for r in cursor.fetchall()]
            context['previous_models'] = previous
        except Exception:
            context['previous_models'] = []

        # Apply focus filter
        if focus_area:
            context['focus_constraint'] = focus_area

        return context

    # ─── (Lens methods handle Phase 2: Creative Synthesis) ──

    # ─── Phase 3: Score Generated Models ────────────────────

    def _score_generated_model(self, model: dict) -> dict:
        """
        Convert a generated business model into the standard opportunity
        format and calculate its weighted score.
        """
        # Map to standard opportunity structure
        opp = {
            # ID is assigned by knowledge_base.save_opportunity()
            'title': model.get('title', 'Untitled Model'),
            'one_liner': model.get('one_liner', ''),
            'source': 'business_model_generator',
            'source_date': datetime.utcnow().strftime('%Y-%m-%d'),
            'sector': model.get('sector', ''),
            'geography': model.get('geography', 'UK'),
            'why_now': model.get('ai_unlock', ''),
            'first_move': model.get('first_move', ''),
            'revenue_path': model.get('business_model', {}).get('pricing', ''),
            'risks': [model.get('kill_criteria', 'Unknown')],
            'tags': model.get('tags', []) + ['generated-model'],
            'type': 'generated_model',
        }

        # Score via Claude API — use EXACT dimension names for reliable parsing
        scoring_prompt = (
            f"Score this business model on EXACTLY these 10 dimensions. "
            f"Use EXACTLY these JSON keys — no renaming, no extras.\n\n"
            f"DIMENSIONS (key → what to evaluate):\n"
            f"1. founder_fit (MULTIPLIER, not additive): How well does this match the operator's specific skills/assets? Score 1-10. The final total will be multiplied by (score/10).\n"
            f"2. ai_unlock (×2.5): Does AI fundamentally enable this or just help?\n"
            f"3. time_to_revenue (×2.5): How quickly can this generate revenue?\n"
            f"4. capital_efficiency (×2.0): How little capital is needed to start?\n"
            f"5. market_timing (×2.0): Is there a timing advantage right now?\n"
            f"6. defensibility (×1.5): Can competitors easily replicate this?\n"
            f"7. scale_potential (×1.5): What is the TAM and scaling path?\n"
            f"8. geographic_leverage (×1.5): Does cross-border positioning create advantage?\n"
            f"9. competition_gap (×1.0): How crowded is the space?\n"
            f"10. simplicity (×1.0): How easy is it to explain and launch?\n\n"
            f"Score each 1-10. Be rigorous and honest.\n\n"
            f"BUSINESS MODEL:\n"
            f"Title: {model.get('title')}\n"
            f"Problem: {model.get('problem')}\n"
            f"Solution: {model.get('solution')}\n"
            f"AI Unlock: {model.get('ai_unlock')}\n"
            f"Customer: {json.dumps(model.get('customer', {}))}\n"
            f"Business Model: {json.dumps(model.get('business_model', {}))}\n"
            f"Founder Edge: {model.get('founder_edge')}\n"
            f"Competitive Landscape: {model.get('competitive_landscape')}\n"
            f"Sector: {model.get('sector')}\n"
            f"Geography: {model.get('geography')}\n\n"
            f"RESPOND WITH ONLY THIS JSON — no explanation before or after:\n"
            f'{{"scores": {{"founder_fit": {{"score": N, "reason": "..."}}, '
            f'"ai_unlock": {{"score": N, "reason": "..."}}, '
            f'"time_to_revenue": {{"score": N, "reason": "..."}}, '
            f'"capital_efficiency": {{"score": N, "reason": "..."}}, '
            f'"market_timing": {{"score": N, "reason": "..."}}, '
            f'"defensibility": {{"score": N, "reason": "..."}}, '
            f'"scale_potential": {{"score": N, "reason": "..."}}, '
            f'"geographic_leverage": {{"score": N, "reason": "..."}}, '
            f'"competition_gap": {{"score": N, "reason": "..."}}, '
            f'"simplicity": {{"score": N, "reason": "..."}}}}}}'
        )

        try:
            scorer_model = self.llm.get_model('scoring')
            response = self.llm.create(
                model=scorer_model,
                max_tokens=2048,
                system=self._system_prompt,
                messages=[{"role": "user", "content": scoring_prompt}]
            )

            text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text += block.text

            scores_data = self._parse_scores(text)
            if not scores_data:
                logger.warning(f"💡 Empty scores for '{model.get('title')}'. "
                             f"Raw text (first 300): {text[:300]}")
            opp['scores'] = scores_data
            opp['weighted_total'] = self._calculate_weighted_total(scores_data)
            opp['tier'] = self._determine_tier(opp['weighted_total'])
            logger.info(f"💡 Scored '{model.get('title')}': "
                       f"{opp['weighted_total']}/155 ({opp['tier']})")

        except Exception as e:
            logger.warning(f"Scoring failed for '{model.get('title')}': {e}")
            opp['scores'] = {}
            opp['weighted_total'] = 0
            opp['tier'] = 'LOW'

        # Merge original model data into opportunity
        opp['generated_model'] = model
        return opp

    # ─── Phase 4: Web Validation ────────────────────────────

    def _web_validate_model(self, model: dict) -> dict:
        """
        Use web search to validate key assumptions of the generated model.
        Adds a 'validation' field with findings.
        """
        title = model.get('title', '')
        gen_data = model.get('generated_model', {})
        customer = gen_data.get('customer', {})

        validation_query = (
            f"Validate this business idea: {title}. "
            f"Search for: 1) Does the target customer ({customer.get('who', 'unknown')}) "
            f"actually have this problem? 2) Are there existing competitors? "
            f"3) What do they charge? 4) Is there recent market activity "
            f"(funding, launches, acquisitions) in this space?"
        )

        try:
            validation_model = self.llm.get_model('scoring')
            messages = [{"role": "user", "content": validation_query}]
            response = self.llm.create(
                model=validation_model,
                max_tokens=2048,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search"
                }],
                messages=messages
            )

            # Multi-turn loop for web search completion
            loop_count = 0
            while response.stop_reason == "tool_use" and loop_count < 15:
                loop_count += 1
                logger.info(f"💡 Validation search loop {loop_count} for '{title[:40]}'")
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
                response = self.llm.create(
                    model=validation_model,
                    max_tokens=2048,
                    tools=[{
                        "type": "web_search_20250305",
                        "name": "web_search"
                    }],
                    messages=messages
                )

            text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text += block.text

            model['validation'] = {
                'status': 'validated',
                'findings': text[:2000],
                'validated_at': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.warning(f"Web validation failed for '{title}': {e}")
            model['validation'] = {
                'status': 'validation_failed',
                'error': str(e)
            }

        return model

    # ─── Phase 5: Storage ───────────────────────────────────

    def _store_model(self, model: dict):
        """Store generated model in both the opportunities table and
        the dedicated generated_models table."""
        # Store as opportunity (for portfolio view and scoring)
        self.kb.save_opportunity(model)

        # Store in dedicated generated_models table
        try:
            gen_data = model.get('generated_model', {})
            cursor = self.kb.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO generated_models
                (id, title, one_liner, origin_story, problem, solution,
                 ai_unlock, customer_json, business_model_json, founder_edge,
                 competitive_landscape, first_move, week_1_plan, kill_criteria,
                 sector, geography, tags_json, confidence, confidence_reasoning,
                 validation_json, weighted_total, tier)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                model.get('id', ''),
                model.get('title', ''),
                model.get('one_liner', ''),
                gen_data.get('origin_story', ''),
                gen_data.get('problem', ''),
                gen_data.get('solution', ''),
                gen_data.get('ai_unlock', ''),
                json.dumps(gen_data.get('customer', {})),
                json.dumps(gen_data.get('business_model', {})),
                gen_data.get('founder_edge', ''),
                gen_data.get('competitive_landscape', ''),
                gen_data.get('first_move', ''),
                gen_data.get('week_1_plan', ''),
                gen_data.get('kill_criteria', ''),
                gen_data.get('sector', ''),
                gen_data.get('geography', ''),
                json.dumps(gen_data.get('tags', [])),
                gen_data.get('confidence', 'MEDIUM'),
                gen_data.get('confidence_reasoning', ''),
                json.dumps(model.get('validation', {})),
                model.get('weighted_total', 0),
                model.get('tier', 'LOW'),
            ))
            self.kb.conn.commit()
        except Exception as e:
            logger.error(f"Failed to store generated model: {e}")

    # ─── Helpers ────────────────────────────────────────────

    def _format_context_for_prompt(self, context: dict) -> str:
        """Format the intelligence context as readable text for the prompt."""
        parts = []

        # Top opportunities
        opps = context.get('top_opportunities', [])
        if opps:
            parts.append(f"TOP {len(opps)} EXISTING OPPORTUNITIES (already found):")
            for o in opps[:10]:
                parts.append(
                    f"  [{o.get('tier')} {o.get('score')}] {o.get('title')} "
                    f"| {o.get('sector')} | Tags: {', '.join(o.get('tags', []))}"
                )
                if o.get('why_now'):
                    parts.append(f"    Why now: {o['why_now'][:150]}")

        # Signals
        signals = context.get('recent_signals', [])
        if signals:
            parts.append(f"\nMARKET SIGNALS ({len(signals)} recent):")
            for s in signals[:20]:
                parts.append(
                    f"  [{s.get('type', '?')}] {s.get('summary', '')}"
                )
                if s.get('potential_opportunities'):
                    parts.append(
                        f"    Potential: {', '.join(s['potential_opportunities'][:3])}"
                    )

        # Trends
        trends = context.get('rising_trends', [])
        if trends:
            parts.append(f"\nRISING TRENDS ({len(trends)} tracked):")
            for t in trends[:15]:
                arrow = {"rising": "↑", "stable": "→", "declining": "↓"}.get(
                    t.get('trajectory', ''), '?'
                )
                parts.append(
                    f"  {arrow} {t.get('keyword')} "
                    f"(mentioned {t.get('mentions')} times)"
                )

        # Cross-pollinations
        cross = context.get('cross_pollinations', [])
        if cross:
            parts.append(f"\nCROSS-POLLINATION INSIGHTS ({len(cross)} unacted):")
            for c in cross[:10]:
                parts.append(f"  💡 {c.get('insight', '')}")
                if c.get('novel_angle'):
                    parts.append(f"     Novel angle: {c['novel_angle']}")

        # Blind spots
        blind = context.get('blind_spots', [])
        if blind:
            parts.append(f"\nBLIND SPOTS & PATTERNS ({len(blind)} detected):")
            for b in blind[:10]:
                parts.append(f"  👁️ {b.get('description', '')}")

        # Top sources
        sources = context.get('top_performing_sources', [])
        if sources:
            parts.append(f"\nHIGHEST-SIGNAL SOURCES:")
            for s in sources[:5]:
                parts.append(
                    f"  {s.get('name')}: {s.get('opps')} opportunities, "
                    f"avg score {s.get('avg_score')}"
                )

        if not any([opps, signals, trends, cross, blind]):
            parts.append(
                "NO ACCUMULATED DATA YET. This is the first generation cycle. "
                "Generate ideas based on the founder profile and general market "
                "knowledge. Future cycles will be data-driven."
            )

        return "\n".join(parts)

    def _parse_models_response(self, text: str) -> list:
        """Extract model list with robust fallback strategies."""
        import re
        if not text or not text.strip():
            return []

        # Strategy 1: Direct parse
        try:
            data = json.loads(text.strip())
            return data.get('models', [])
        except json.JSONDecodeError:
            pass

        # Strategy 2: Code fence
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1).strip())
                return data.get('models', [])
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find first '{' and parse from there
        first_brace = text.find('{')
        if first_brace >= 0:
            json_candidate = text[first_brace:]
            try:
                data = json.loads(json_candidate)
                return data.get('models', [])
            except json.JSONDecodeError:
                pass

            # Strategy 4: Repair truncated JSON
            repaired = self._repair_truncated_json(json_candidate)
            if repaired:
                try:
                    data = json.loads(repaired)
                    return data.get('models', [])
                except json.JSONDecodeError:
                    pass

        logger.warning("Could not parse models from Opus response")
        logger.warning(f"Raw text (first 500): {text[:500]}")
        return []

    def _parse_scores(self, text: str) -> dict:
        """Extract scores dict with robust fallback strategies."""
        import re
        if not text or not text.strip():
            return {}

        # Strategy 1: Direct parse
        try:
            data = json.loads(text.strip())
            return data.get('scores', data)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Code fence
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1).strip())
                return data.get('scores', data)
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find first '{' and parse from there
        first_brace = text.find('{')
        if first_brace >= 0:
            json_candidate = text[first_brace:]
            try:
                data = json.loads(json_candidate)
                return data.get('scores', data)
            except json.JSONDecodeError:
                pass

            # Strategy 4: Repair truncated JSON
            repaired = self._repair_truncated_json(json_candidate)
            if repaired:
                try:
                    data = json.loads(repaired)
                    return data.get('scores', data)
                except json.JSONDecodeError:
                    pass

        logger.warning("Could not parse scores from response")
        return {}

    @staticmethod
    def _repair_truncated_json(text: str) -> str:
        """Repair truncated JSON by closing open brackets/braces."""
        if not text:
            return ""
        depth_brace = 0
        depth_bracket = 0
        last_safe_pos = 0
        in_string = False
        escape_next = False

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
            if ch == '{':
                depth_brace += 1
            elif ch == '}':
                depth_brace -= 1
                if depth_brace >= 0:
                    last_safe_pos = i + 1
            elif ch == '[':
                depth_bracket += 1
            elif ch == ']':
                depth_bracket -= 1

        if depth_brace == 0 and depth_bracket == 0:
            return text

        repaired = text[:last_safe_pos]
        depth_brace = 0
        depth_bracket = 0
        in_string = False
        escape_next = False
        for ch in repaired:
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
            if ch == '{':
                depth_brace += 1
            elif ch == '}':
                depth_brace -= 1
            elif ch == '[':
                depth_bracket += 1
            elif ch == ']':
                depth_bracket -= 1

        repaired += ']' * depth_bracket + '}' * depth_brace
        return repaired

    def _calculate_weighted_total(self, scores: dict) -> float:
        """Delegates to scoring_utils."""
        return calculate_weighted_total(scores, self.config)

    def _determine_tier(self, weighted_total: float) -> str:
        """Delegates to scoring_utils."""
        return determine_tier(weighted_total, self.config)

    def _load_founder_profile(self) -> str:
        """Load founder profile YAML as text."""
        try:
            return FOUNDER_PROFILE_PATH.read_text(encoding='utf-8')
        except FileNotFoundError:
            return "Founder profile not available."

    def _load_system_prompt(self) -> str:
        """Load the analysis system prompt."""
        try:
            return SYSTEM_PROMPT_PATH.read_text(encoding='utf-8')
        except FileNotFoundError:
            return "Score opportunities on 10 dimensions. Return JSON."
