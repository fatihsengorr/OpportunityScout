"""
OpportunityScout — Self-Improvement Engine (Closed-Loop v2)

Analyzes the scout's own performance and APPLIES corrections:
- Auto-adjusts source tiers based on performance (read/write sources.yaml)
- Auto-calibrates scoring weights based on operator feedback (read/write config.yaml)
- Identifies blind spots using ALL capability clusters (from capability_map.yaml)
- Publishes blind_spot_found events to trigger capability explorer
- Detects meta-patterns across opportunities
- Tracks strategy performance and reallocates resources
"""

import json
import logging
import yaml
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("scout.evolve")


class SelfImprover:
    """
    The evolution engine. Makes the scout smarter every cycle.
    Now with CLOSED LOOPS — detects AND applies changes automatically.
    """

    def __init__(self, config: dict, knowledge_base, event_bus=None):
        self.config = config
        self.kb = knowledge_base
        self.event_bus = event_bus
        self.evolution_log_path = Path("./data/evolution_log.md")
        self.sources_path = Path("./config/sources.yaml")
        self.config_path = Path("./config/config.yaml")
        self.capability_map_path = Path("./config/capability_map.yaml")
        self._ensure_log_file()

    def run_evolution_cycle(self) -> list:
        """
        Run a full self-improvement cycle. Returns list of changes made.
        Called weekly by the scheduler.
        """
        changes = []
        cycle_time = datetime.utcnow().isoformat()

        logger.info("🧬 Starting evolution cycle (closed-loop v2)...")

        # 1. Audit source performance + AUTO-APPLY tier changes
        source_changes = self._audit_sources()
        changes.extend(source_changes)

        # 2. Calibrate scoring based on feedback + AUTO-APPLY weight changes
        scoring_changes = self._calibrate_scoring()
        changes.extend(scoring_changes)

        # 3. Detect meta-patterns
        patterns = self._detect_patterns()
        changes.extend(patterns)

        # 4. Identify blind spots using ALL capabilities + PUBLISH events
        blind_spots = self._identify_blind_spots()
        changes.extend(blind_spots)

        # 5. Analyze strategy performance across all engines
        strategy_changes = self._analyze_strategy_performance()
        changes.extend(strategy_changes)

        # 6. Update evolution log file
        self._write_evolution_log(cycle_time, changes)

        logger.info(f"🧬 Evolution cycle complete: {len(changes)} changes")
        return changes

    # ─── Source Tier Auto-Adjustment ────────────────────────

    def _audit_sources(self) -> list:
        """
        Analyze source performance and AUTO-APPLY tier changes.
        - 0 opps in 4+ scans → demote tier (1→2, 2→3)
        - Star performer → promote tier (3→2, 2→1)
        - High error rate → flag for review
        """
        changes = []
        performance = self.kb.get_source_performance(days=30)

        if not performance:
            return changes

        demotions = []
        promotions = []

        for source in performance:
            name = source['source_name']
            total_opps = source['total_opportunities']
            total_items = source['total_items']
            mean_score = source.get('mean_score', 0)
            scan_count = source['scan_count']
            errors = source.get('total_errors', 0)
            best_score = source.get('best_score', 0)

            # Calculate signal-to-noise ratio
            snr = total_opps / total_items if total_items > 0 else 0

            # AUTO-DEMOTE: 0 opps in 4+ scans
            if scan_count >= 4 and total_opps == 0:
                demotions.append(name)
                change = {
                    "type": "source_demoted",
                    "description": (
                        f"Source '{name}' AUTO-DEMOTED: 0 opportunities "
                        f"in {scan_count} scans. Tier reduced."
                    ),
                    "action": "applied"
                }
                changes.append(change)
                self.kb.log_evolution(
                    "source_demote", change["description"],
                    old_value=f"snr={snr:.2f}", new_value="tier_down",
                    reasoning=f"{scan_count} scans, 0 opportunities"
                )

            # AUTO-PROMOTE: star performer (3+ opps AND avg score > 100)
            elif total_opps >= 3 and mean_score > 100:
                promotions.append(name)
                change = {
                    "type": "source_promoted",
                    "description": (
                        f"Source '{name}' AUTO-PROMOTED: {total_opps} opps, "
                        f"avg score {mean_score:.0f}, best {best_score:.0f}. "
                        f"Tier increased."
                    ),
                    "action": "applied"
                }
                changes.append(change)
                self.kb.log_evolution(
                    "source_promote", change["description"],
                    old_value=f"snr={snr:.2f}", new_value="tier_up",
                    reasoning=f"{total_opps} opportunities, avg {mean_score:.0f}"
                )

            # Flag high-error sources
            if errors > scan_count * 0.5 and scan_count >= 3:
                change = {
                    "type": "source_error",
                    "description": (
                        f"Source '{name}' has high error rate: "
                        f"{errors}/{scan_count} scans failed."
                    ),
                    "action": "review_needed"
                }
                changes.append(change)

        # Apply tier changes to sources.yaml
        if demotions or promotions:
            self._apply_source_tier_changes(demotions, promotions)

        return changes

    def _apply_source_tier_changes(self, demotions: list, promotions: list):
        """Read sources.yaml, adjust tiers, write back."""
        try:
            with open(self.sources_path) as f:
                data = yaml.safe_load(f)

            sources = data.get('sources', [])
            modified = False

            for source in sources:
                name = source.get('name', '')
                current_tier = source.get('tier', 2)

                if name in demotions and current_tier < 3:
                    source['tier'] = current_tier + 1
                    logger.info(f"🔻 Source '{name}' demoted: Tier {current_tier} → {current_tier + 1}")
                    modified = True
                elif name in promotions and current_tier > 1:
                    source['tier'] = current_tier - 1
                    logger.info(f"🔺 Source '{name}' promoted: Tier {current_tier} → {current_tier - 1}")
                    modified = True

            if modified:
                with open(self.sources_path, 'w') as f:
                    yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                logger.info("✅ sources.yaml updated with tier changes")

        except Exception as e:
            logger.error(f"Failed to apply source tier changes: {e}")

    # ─── Scoring Weight Auto-Calibration ────────────────────

    def _calibrate_scoring(self) -> list:
        """
        If operator has provided feedback (ratings on opportunities),
        use it to detect scoring dimension biases and AUTO-APPLY weight corrections.
        """
        changes = []

        # Get opportunities with operator ratings
        rated_opps = self.kb.get_top_opportunities(limit=100, status='reviewed')
        rated_opps = [o for o in rated_opps if o.get('operator_rating') is not None]

        if len(rated_opps) < 5:
            return changes  # Need minimum feedback to calibrate

        # Compare operator rating (1-5) with our tier prediction
        over_scored = []
        under_scored = []

        for opp in rated_opps:
            our_tier = opp.get('tier', '')
            operator_rating = opp.get('operator_rating', 3)

            if operator_rating >= 5 and our_tier in ['LOW', 'MEDIUM']:
                under_scored.append(opp)
            elif operator_rating <= 2 and our_tier in ['FIRE', 'HIGH']:
                over_scored.append(opp)

        weight_adjustments = {}

        if over_scored:
            over_dims = self._find_biased_dimensions(over_scored, 'over')
            if over_dims:
                for dim in over_dims:
                    weight_adjustments[dim] = -0.1  # Reduce by 0.1
                change = {
                    "type": "scoring_calibration",
                    "description": (
                        f"AUTO-APPLIED: Reduced weights for over-scoring dimensions: "
                        f"{', '.join(over_dims)} (by -0.1 each). "
                        f"Based on {len(over_scored)} over-scored opportunities."
                    ),
                    "action": "applied"
                }
                changes.append(change)
                self.kb.log_evolution(
                    "weight_adjustment", change["description"],
                    old_value=json.dumps(over_dims),
                    new_value="weights reduced by 0.1",
                    reasoning="Operator feedback indicates over-scoring"
                )

        if under_scored:
            under_dims = self._find_biased_dimensions(under_scored, 'under')
            if under_dims:
                for dim in under_dims:
                    weight_adjustments[dim] = 0.1  # Increase by 0.1
                change = {
                    "type": "scoring_calibration",
                    "description": (
                        f"AUTO-APPLIED: Increased weights for under-scoring dimensions: "
                        f"{', '.join(under_dims)} (by +0.1 each). "
                        f"Based on {len(under_scored)} under-scored opportunities."
                    ),
                    "action": "applied"
                }
                changes.append(change)

        # Apply weight changes to config.yaml
        if weight_adjustments:
            self._apply_weight_adjustments(weight_adjustments)

        return changes

    def _apply_weight_adjustments(self, adjustments: dict):
        """
        Read config.yaml, adjust scoring weights, write back.
        Clamps weights to [0.5, 5.0] range to prevent runaway.
        """
        try:
            with open(self.config_path) as f:
                data = yaml.safe_load(f)

            weights = data.get('scoring', {}).get('weights', {})
            modified = False

            for dim, delta in adjustments.items():
                if dim in weights:
                    old_val = weights[dim]
                    new_val = round(max(0.5, min(5.0, old_val + delta)), 1)
                    if new_val != old_val:
                        weights[dim] = new_val
                        logger.info(f"⚖️ Weight '{dim}': {old_val} → {new_val} (delta={delta:+.1f})")
                        modified = True

            if modified:
                with open(self.config_path, 'w') as f:
                    yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                logger.info("✅ config.yaml updated with weight adjustments")

        except Exception as e:
            logger.error(f"Failed to apply weight adjustments: {e}")

    # ─── Pattern Detection ──────────────────────────────────

    def _detect_patterns(self) -> list:
        """
        Look for meta-patterns across all opportunities.
        What themes keep appearing? What's rising vs declining?
        """
        changes = []

        recent = self.kb.get_recent_opportunities(hours=168)  # Last 7 days
        if len(recent) < 3:
            return changes

        # Count sector frequency
        sector_counts = {}
        tag_counts = {}
        for opp in recent:
            sector = opp.get('sector', 'Unknown')
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
            for tag in opp.get('tags', []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Find dominant sectors/tags
        if sector_counts:
            top_sector = max(sector_counts, key=sector_counts.get)
            total = len(recent)
            top_count = sector_counts[top_sector]

            # Warn if a single sector dominates > 40%
            if total > 5 and top_count / total > 0.4:
                change = {
                    "type": "sector_concentration",
                    "description": (
                        f"⚠️ Sector concentration warning: '{top_sector}' is "
                        f"{top_count}/{total} ({top_count/total*100:.0f}%) of "
                        f"opportunities this week. Portfolio diversity needs attention."
                    ),
                    "action": "diversify_sources"
                }
                changes.append(change)

                # Publish to event bus
                if self.event_bus:
                    self.event_bus.publish('blind_spot_found', {
                        'type': 'sector_concentration',
                        'dominant_sector': top_sector,
                        'percentage': round(top_count / total * 100, 1),
                        'recommendation': 'Increase exploration in non-construction sectors'
                    }, source_module='self_improver')

            elif top_count >= 3:
                change = {
                    "type": "pattern_detected",
                    "description": (
                        f"Pattern: '{top_sector}' sector appeared in "
                        f"{top_count}/{total} opportunities this week. "
                        f"May indicate a trending opportunity area."
                    ),
                    "action": "investigate_cluster"
                }
                changes.append(change)

        if tag_counts:
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            rising_tags = [t for t, c in top_tags if c >= 3]
            if rising_tags:
                change = {
                    "type": "pattern_detected",
                    "description": (
                        f"Rising tags this week: {', '.join(rising_tags)}. "
                        f"These themes are clustering — may indicate convergent opportunity."
                    ),
                    "action": "deep_dive_recommended"
                }
                changes.append(change)

        return changes

    # ─── Blind Spot Detection (All Capabilities) ────────────

    def _identify_blind_spots(self) -> list:
        """
        Check if capability clusters from capability_map.yaml are underexploited.
        Uses ALL capability clusters (not hardcoded construction tags).
        Publishes blind_spot_found events so capability explorer can act.
        """
        changes = []

        recent = self.kb.get_recent_opportunities(hours=720)  # Last 30 days
        if not recent:
            return changes

        # Collect all tags/sectors from recent opportunities
        all_tags = set()
        all_sectors = set()
        for opp in recent:
            all_tags.update(t.lower() for t in opp.get('tags', []))
            sector = opp.get('sector', '').lower()
            if sector:
                all_sectors.add(sector)

        # Load capability clusters from capability_map.yaml
        capability_tags = self._load_capability_tags()

        for cluster_name, cluster_info in capability_tags.items():
            keywords = cluster_info.get('keywords', [])
            weight = cluster_info.get('weight', 1.0)

            # Check if ANY keyword from this cluster appears in recent tags/sectors
            matched = any(
                any(kw in tag for tag in all_tags) or any(kw in sec for sec in all_sectors)
                for kw in keywords
            )

            if not matched:
                description = cluster_info.get('description', cluster_name)
                change = {
                    "type": "blind_spot",
                    "description": (
                        f"Blind spot: '{cluster_name}' capability cluster "
                        f"(weight={weight}) has ZERO matches in last 30 days. "
                        f"{description}"
                    ),
                    "action": "explore_capability"
                }
                changes.append(change)

                # Publish to event bus so capability explorer picks it up
                if self.event_bus:
                    self.event_bus.publish('blind_spot_found', {
                        'type': 'capability_underexploited',
                        'capability': cluster_name,
                        'weight': weight,
                        'keywords': keywords,
                        'days_without_match': 30
                    }, source_module='self_improver')

                    logger.info(
                        f"👁️ Blind spot published: {cluster_name} "
                        f"(weight={weight}, 0 matches in 30 days)"
                    )

        return changes

    def _load_capability_tags(self) -> dict:
        """
        Load capability clusters from capability_map.yaml.
        Returns dict of cluster_name → {keywords, weight, description}.
        Falls back to basic defaults if file not found.
        """
        try:
            with open(self.capability_map_path) as f:
                data = yaml.safe_load(f)

            clusters = {}
            for cluster_name, cluster_data in data.get('capabilities', {}).items():
                # Extract search keywords from the cluster
                keywords = []
                # Use cluster name variants as keywords
                keywords.append(cluster_name.replace('_', ' '))
                keywords.append(cluster_name.replace('_', '-'))

                # Add adjacent industry names as keywords
                for industry in cluster_data.get('adjacent_industries', []):
                    if isinstance(industry, dict):
                        ind_name = industry.get('name', '')
                    else:
                        ind_name = str(industry)
                    keywords.append(ind_name.replace('_', ' '))
                    keywords.append(ind_name.replace('_', '-'))

                # Add core skills as keywords
                for skill in cluster_data.get('core_skills', []):
                    keywords.append(skill.lower())

                clusters[cluster_name] = {
                    'keywords': [k.lower() for k in keywords if k],
                    'weight': cluster_data.get('weight', 1.0),
                    'description': cluster_data.get('description',
                                                     f'{cluster_name} capabilities are underexploited')
                }

            return clusters

        except FileNotFoundError:
            logger.warning("capability_map.yaml not found, using basic defaults")
            return {
                'it_infrastructure': {
                    'keywords': ['it infrastructure', 'cybersecurity', 'managed soc', 'vdi', 'disaster recovery'],
                    'weight': 2.0,
                    'description': 'IT infrastructure expertise (20yr deep) is completely underexploited'
                },
                'ai_software': {
                    'keywords': ['ai', 'saas', 'automation', 'workflow', 'machine learning'],
                    'weight': 1.5,
                    'description': 'AI/Software development capabilities underutilized'
                },
                'cross_border': {
                    'keywords': ['cross-border', 'export', 'import', 'trade', 'arbitrage', 'localization'],
                    'weight': 1.5,
                    'description': 'Cross-border trade expertise (UK-Turkey-UAE) underutilized'
                },
                'manufacturing': {
                    'keywords': ['manufacturing', 'coil coating', 'chemical', 'surface treatment'],
                    'weight': 1.0,
                    'description': 'Manufacturing & chemicals expertise underutilized'
                },
                'construction': {
                    'keywords': ['construction', 'bim', 'fire door', 'fitout', 'building safety'],
                    'weight': 0.5,
                    'description': 'Construction sector (typically over-explored)'
                }
            }

    # ─── Strategy Performance Analysis ──────────────────────

    def _analyze_strategy_performance(self) -> list:
        """
        Analyze which discovery strategies perform best.
        Recommends reallocation based on ROI (opportunities per dollar).
        """
        changes = []

        try:
            perf = self.kb.get_strategy_performance(days=30)
        except Exception:
            return changes

        if not perf or len(perf) < 2:
            return changes

        # Group by strategy
        strategy_stats = {}
        for row in perf:
            name = row.get('strategy_name', 'unknown')
            if name not in strategy_stats:
                strategy_stats[name] = {
                    'runs': 0, 'total_opps': 0, 'total_fire': 0,
                    'total_high': 0, 'total_cost': 0, 'best_score': 0
                }
            s = strategy_stats[name]
            s['runs'] += 1
            s['total_opps'] += row.get('opportunities_found', 0)
            s['total_fire'] += row.get('fire_count', 0)
            s['total_high'] += row.get('high_count', 0)
            s['total_cost'] += row.get('cost_usd', 0)
            s['best_score'] = max(s['best_score'], row.get('best_score', 0))

        # Find best and worst strategies
        if len(strategy_stats) >= 2:
            ranked = sorted(
                strategy_stats.items(),
                key=lambda x: x[1]['total_fire'] * 3 + x[1]['total_high'] * 2 + x[1]['total_opps'],
                reverse=True
            )

            best_name, best_stats = ranked[0]
            worst_name, worst_stats = ranked[-1]

            # Report
            change = {
                "type": "strategy_analysis",
                "description": (
                    f"Strategy Performance (30d): "
                    f"BEST='{best_name}' ({best_stats['total_fire']}🔥 "
                    f"{best_stats['total_high']}⭐ in {best_stats['runs']} runs) | "
                    f"WORST='{worst_name}' ({worst_stats['total_fire']}🔥 "
                    f"{worst_stats['total_high']}⭐ in {worst_stats['runs']} runs). "
                    f"Consider allocating more resources to {best_name}."
                ),
                "action": "strategy_rebalance"
            }
            changes.append(change)

        return changes

    # ─── Helpers ────────────────────────────────────────────

    def _find_biased_dimensions(self, opps: list, direction: str) -> list:
        """Find which scoring dimensions are consistently biased."""
        dim_totals = {}
        dim_counts = {}

        for opp in opps:
            scores = opp.get('scores', {})
            for dim, data in scores.items():
                score = data.get('score', 5) if isinstance(data, dict) else data
                dim_totals[dim] = dim_totals.get(dim, 0) + score
                dim_counts[dim] = dim_counts.get(dim, 0) + 1

        biased = []
        for dim in dim_totals:
            avg = dim_totals[dim] / dim_counts[dim]
            if direction == 'over' and avg >= 7:
                biased.append(dim)
            elif direction == 'under' and avg <= 4:
                biased.append(dim)

        return biased

    def _ensure_log_file(self):
        """Ensure the evolution log file exists."""
        self.evolution_log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.evolution_log_path.exists():
            self.evolution_log_path.write_text(
                "# OpportunityScout — Evolution Log\n\n"
                "This log tracks all self-improvement actions taken by the scout.\n\n"
                "---\n\n"
            )

    def _write_evolution_log(self, cycle_time: str, changes: list):
        """Append evolution cycle results to the log file."""
        with open(self.evolution_log_path, 'a') as f:
            f.write(f"\n## Evolution Cycle — {cycle_time}\n\n")
            if changes:
                for change in changes:
                    emoji = {
                        'source_demoted': '🔻',
                        'source_promoted': '🔺',
                        'source_review': '🔍',
                        'source_error': '⚠️',
                        'scoring_calibration': '⚖️',
                        'pattern_detected': '🔮',
                        'sector_concentration': '🚨',
                        'blind_spot': '👁️',
                        'strategy_analysis': '📊',
                    }.get(change.get('type', ''), '📝')
                    f.write(f"- {emoji} **{change.get('type', 'unknown')}**: "
                           f"{change.get('description', '')}\n")
            else:
                f.write("- No changes this cycle. System performing well.\n")
            f.write("\n---\n")
