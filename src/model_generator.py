"""
OpportunityScout — Business Model Generator

This is the CREATIVE brain of the scout. Unlike the scanner which finds
existing opportunities, this module INVENTS new business models by:

1. Analyzing accumulated signals, trends, and gaps in the knowledge base
2. Cross-referencing with the founder's unique capability map
3. Identifying structural market inefficiencies nobody is solving
4. Designing complete business models with unit economics
5. Scoring them through the standard 10-dimension pipeline

Runs weekly (or on demand via /generate command).
Uses Claude Opus for maximum creative and analytical depth.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from anthropic import Anthropic

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
        self.client = Anthropic(
            api_key=config.get('claude', {}).get('api_key')
            or os.environ.get('ANTHROPIC_API_KEY')
        )
        # Always use Opus for creative synthesis — this is the highest-value task
        self.model = config.get('claude', {}).get(
            'model_deep_dive', 'claude-opus-4-20250514'
        )
        self.max_tokens = 8192
        self._founder_profile = self._load_founder_profile()
        self._system_prompt = self._load_system_prompt()

    def generate(self, focus_area: str = None, count: int = 3) -> dict:
        """
        Generate novel business model ideas from accumulated intelligence.

        Args:
            focus_area: Optional focus constraint (e.g., "scan-to-bim", 
                       "fire-doors", "cross-border"). If None, generates
                       across all domains.
            count: Number of business models to generate (default 3).

        Returns:
            dict with "models" list, each containing full business model
            specification + standard opportunity scoring.
        """
        logger.info(f"💡 Generating {count} business models"
                    f"{f' (focus: {focus_area})' if focus_area else ''}...")

        # Phase 1: Gather accumulated intelligence from knowledge base
        context = self._build_intelligence_context(focus_area)

        # Phase 2: Send to Opus with creative synthesis prompt
        raw_models = self._call_opus_for_generation(context, focus_area, count)

        # Phase 3: Score each generated model through standard pipeline
        scored_models = []
        for model in raw_models:
            scored = self._score_generated_model(model)
            scored_models.append(scored)

        # Phase 4: Web-validate the top models
        validated_models = []
        for model in sorted(scored_models,
                           key=lambda m: m.get('weighted_total', 0),
                           reverse=True)[:count]:
            validated = self._web_validate_model(model)
            validated_models.append(validated)

        # Phase 5: Store in knowledge base
        for model in validated_models:
            self._store_model(model)

        result = {
            "models": validated_models,
            "generation_context": {
                "signals_analyzed": context.get('signal_count', 0),
                "trends_analyzed": context.get('trend_count', 0),
                "blind_spots_found": context.get('blind_spot_count', 0),
                "focus_area": focus_area,
                "timestamp": datetime.utcnow().isoformat()
            }
        }

        logger.info(f"💡 Generated {len(validated_models)} business models")
        return result

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

    # ─── Phase 2: Creative Synthesis with Opus ──────────────

    def _call_opus_for_generation(self, context: dict,
                                  focus_area: str = None,
                                  count: int = 3) -> list:
        """
        Send accumulated intelligence to Claude Opus with a creative
        synthesis prompt. This is where new business models are invented.
        """
        # Build the context summary
        context_text = self._format_context_for_prompt(context)

        focus_instruction = ""
        if focus_area:
            focus_instruction = (
                f"\n\nFOCUS CONSTRAINT: Generate models specifically in or "
                f"related to: {focus_area}. But don't force it — if the data "
                f"doesn't support strong ideas in this area, say so and suggest "
                f"where the real opportunity lies.\n"
            )

        previous_models = context.get('previous_models', [])
        avoid_text = ""
        if previous_models:
            titles = [m['title'] for m in previous_models]
            avoid_text = (
                f"\n\nAVOID REPETITION: These models have already been generated. "
                f"Do NOT repeat them or generate close variants:\n"
                f"{chr(10).join(f'- {t}' for t in titles)}\n"
            )

        prompt = f"""You are the creative synthesis engine of OpportunityScout, an autonomous business intelligence system. Your job is NOT to find existing opportunities — the scanner does that. Your job is to INVENT new business models that nobody else can see.

You have access to accumulated intelligence gathered over time: market signals, trending topics, cross-pollination insights, blind spots, and the operator's unique capability map.

YOUR MISSION: Analyze all the intelligence below and generate exactly {count} novel business model ideas. Each must be:

1. GENUINELY NOVEL — not a repackaging of an existing opportunity in the database
2. STRUCTURALLY GROUNDED — based on real signals, trends, or gaps in the data, not fantasy
3. FOUNDER-SPECIFIC — leverages this specific operator's unfair advantages
4. ACTIONABLE — includes a concrete first step that can be taken this week
5. MONETIZABLE — has a clear, specific path to revenue within 90 days

OPERATOR PROFILE:
{self._founder_profile}
{focus_instruction}{avoid_text}

ACCUMULATED INTELLIGENCE:
{context_text}

For EACH business model, provide this EXACT JSON structure:

```json
{{
  "models": [
    {{
      "id": "GEN-{{YYYYMMDD}}-{{N}}",
      "title": "Specific, memorable name",
      "one_liner": "One sentence that makes an investor lean forward",
      "origin_story": "What specific signals/trends/gaps in the data led to this idea? Connect the dots explicitly.",
      "problem": "What specific, painful problem does this solve? Who has this problem? How do they currently cope?",
      "solution": "What exactly do we build/offer? Be specific about the product/service.",
      "ai_unlock": "What specific AI capability makes this possible NOW that wasn't possible 12 months ago?",
      "customer": {{
        "who": "Exact buyer persona (job title, company type, size)",
        "pain_level": "1-10 how painful is this problem?",
        "current_spend": "What do they currently pay for inferior alternatives?",
        "decision_maker": "Who signs the check?"
      }},
      "business_model": {{
        "revenue_type": "SaaS|Service|Marketplace|Product|Licensing|Hybrid",
        "pricing": "Specific pricing with tiers if applicable",
        "unit_economics": "CAC, LTV, margin estimates with reasoning",
        "time_to_first_revenue": "Realistic estimate in days/weeks"
      }},
      "founder_edge": "Why can THIS specific operator win here when others can't? Be specific about which assets/skills/knowledge create the unfair advantage.",
      "competitive_landscape": "Who else could do this? Why haven't they? What's the moat?",
      "first_move": "Exact action to take in the next 48 hours to start validating this",
      "week_1_plan": "Day-by-day plan for the first week",
      "kill_criteria": "What would prove this idea is wrong? At what point do we walk away?",
      "sector": "Primary sector",
      "geography": "UK|US|TR|UAE|Global",
      "tags": ["tag1", "tag2", "tag3"],
      "confidence": "HIGH|MEDIUM|LOW — how confident are you this is real?",
      "confidence_reasoning": "Why this confidence level?"
    }}
  ]
}}
```

CRITICAL RULES:
- Every idea must trace back to specific signals or trends in the accumulated intelligence. No hand-waving.
- "AI consulting" is NOT a business model. "AI-powered fire door compliance verification for UK social housing, sold to building managers at £50/door/year via a mobile app" IS a business model.
- If you can't find {count} genuinely strong ideas, generate fewer. Quality over quantity. Never pad with weak ideas.
- Think like a founder who needs to feed their family, not like a consultant writing a report.
- The best ideas are often boring to VCs but lucrative to operators. Don't chase sexiness.
- Cross-border arbitrage (Turkish cost, UK price) is a SUPERPOWER. Use it.
- Regulation-driven demand (Building Safety Act, ISO 19650, Net Zero) is the most reliable demand. Prioritize it."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search"
                }],
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Extract text content
            text_content = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text_content += block.text

            return self._parse_models_response(text_content)

        except Exception as e:
            logger.error(f"Opus generation failed: {e}")
            return []

    # ─── Phase 3: Score Generated Models ────────────────────

    def _score_generated_model(self, model: dict) -> dict:
        """
        Convert a generated business model into the standard opportunity
        format and calculate its weighted score.
        """
        # Map to standard opportunity structure
        opp = {
            'id': model.get('id', f"GEN-{datetime.utcnow().strftime('%Y%m%d')}-001"),
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

        # Score via Claude API
        scoring_prompt = (
            f"Score this business model against the 10-dimension scoring model. "
            f"Be rigorous.\n\n"
            f"BUSINESS MODEL:\n"
            f"Title: {model.get('title')}\n"
            f"Problem: {model.get('problem')}\n"
            f"Solution: {model.get('solution')}\n"
            f"AI Unlock: {model.get('ai_unlock')}\n"
            f"Customer: {json.dumps(model.get('customer', {}))}\n"
            f"Business Model: {json.dumps(model.get('business_model', {}))}\n"
            f"Founder Edge: {model.get('founder_edge')}\n"
            f"Competitive Landscape: {model.get('competitive_landscape')}\n\n"
            f"Return scores as JSON with 'scores' object containing each "
            f"dimension with 'score' (1-10) and 'reason' fields."
        )

        try:
            scorer_model = self.config.get('claude', {}).get(
                'model', 'claude-sonnet-4-20250514'
            )
            response = self.client.messages.create(
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
            opp['scores'] = scores_data
            opp['weighted_total'] = self._calculate_weighted_total(scores_data)
            opp['tier'] = self._determine_tier(opp['weighted_total'])

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
            response = self.client.messages.create(
                model=self.config.get('claude', {}).get(
                    'model', 'claude-sonnet-4-20250514'
                ),
                max_tokens=2048,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search"
                }],
                messages=[{
                    "role": "user",
                    "content": validation_query
                }]
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
        """Extract model list from Claude's response."""
        import re
        try:
            data = json.loads(text)
            return data.get('models', [])
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return data.get('models', [])
            except json.JSONDecodeError:
                pass

        json_match = re.search(r'\{[\s\S]*"models"[\s\S]*\}', text)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                return data.get('models', [])
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse models from Opus response")
        return []

    def _parse_scores(self, text: str) -> dict:
        """Extract scores dict from Claude's response."""
        import re
        try:
            data = json.loads(text)
            return data.get('scores', data)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'\{[\s\S]*"scores"[\s\S]*\}', text)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                return data.get('scores', data)
            except json.JSONDecodeError:
                pass

        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return data.get('scores', data)
            except json.JSONDecodeError:
                pass

        return {}

    def _calculate_weighted_total(self, scores: dict) -> float:
        """Calculate weighted total from dimension scores."""
        weights = self.config.get('scoring', {}).get('weights', {
            'founder_fit': 3.0, 'ai_unlock': 2.5, 'time_to_revenue': 2.5,
            'capital_efficiency': 2.0, 'market_timing': 2.0,
            'defensibility': 1.5, 'scale_potential': 1.5,
            'geographic_leverage': 1.5, 'competition_gap': 1.0,
            'simplicity': 1.0
        })
        total = 0.0
        for dim, weight in weights.items():
            score_data = scores.get(dim, {})
            score = score_data.get('score', 0) if isinstance(score_data, dict) else (
                score_data if isinstance(score_data, (int, float)) else 0
            )
            total += score * weight
        return round(total, 1)

    def _determine_tier(self, weighted_total: float) -> str:
        thresholds = self.config.get('scoring', {}).get('tiers', {
            'fire': 150, 'high': 120, 'medium': 90
        })
        if weighted_total >= thresholds.get('fire', 150):
            return 'FIRE'
        elif weighted_total >= thresholds.get('high', 120):
            return 'HIGH'
        elif weighted_total >= thresholds.get('medium', 90):
            return 'MEDIUM'
        return 'LOW'

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
