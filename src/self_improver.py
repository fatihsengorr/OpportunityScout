"""
OpportunityScout — Self-Improvement Engine

Analyzes the scout's own performance and evolves its behavior:
- Adjusts source weights based on signal quality
- Calibrates scoring dimensions based on operator feedback
- Identifies blind spots and adds new sources
- Removes low-signal sources
- Detects meta-patterns across opportunities
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("scout.evolve")


class SelfImprover:
    """
    The evolution engine. Makes the scout smarter every cycle.
    """

    def __init__(self, config: dict, knowledge_base):
        self.config = config
        self.kb = knowledge_base
        self.evolution_log_path = Path("./data/evolution_log.md")
        self._ensure_log_file()

    def run_evolution_cycle(self) -> list:
        """
        Run a full self-improvement cycle. Returns list of changes made.
        Called weekly by the scheduler.
        """
        changes = []
        cycle_time = datetime.utcnow().isoformat()

        logger.info("🧬 Starting evolution cycle...")

        # 1. Audit source performance
        source_changes = self._audit_sources()
        changes.extend(source_changes)

        # 2. Calibrate scoring based on feedback
        scoring_changes = self._calibrate_scoring()
        changes.extend(scoring_changes)

        # 3. Detect meta-patterns
        patterns = self._detect_patterns()
        changes.extend(patterns)

        # 4. Identify blind spots
        blind_spots = self._identify_blind_spots()
        changes.extend(blind_spots)

        # 5. Update evolution log file
        self._write_evolution_log(cycle_time, changes)

        logger.info(f"🧬 Evolution cycle complete: {len(changes)} changes")
        return changes

    def _audit_sources(self) -> list:
        """
        Analyze which sources produce the best opportunities.
        Adjust signal_scores and recommend additions/removals.
        """
        changes = []
        performance = self.kb.get_source_performance(days=30)

        if not performance:
            return changes

        for source in performance:
            name = source['source_name']
            total_opps = source['total_opportunities']
            total_items = source['total_items']
            mean_score = source.get('mean_score', 0)
            scan_count = source['scan_count']
            errors = source.get('total_errors', 0)

            # Calculate signal-to-noise ratio
            if total_items > 0:
                snr = total_opps / total_items
            else:
                snr = 0

            # Flag underperforming sources
            if scan_count >= 4 and total_opps == 0:
                change = {
                    "type": "source_review",
                    "description": (
                        f"Source '{name}' has produced 0 opportunities "
                        f"in {scan_count} scans. Consider removing or "
                        f"adjusting search queries."
                    ),
                    "action": "review_needed"
                }
                changes.append(change)
                self.kb.log_evolution(
                    "source_review", change["description"],
                    old_value=f"snr={snr:.2f}", new_value="review_needed",
                    reasoning=f"{scan_count} scans, 0 opportunities"
                )

            # Flag high-error sources
            if errors > scan_count * 0.5:
                change = {
                    "type": "source_error",
                    "description": (
                        f"Source '{name}' has high error rate: "
                        f"{errors}/{scan_count} scans failed."
                    ),
                    "action": "fix_or_remove"
                }
                changes.append(change)

            # Celebrate top performers
            if total_opps > 3 and mean_score > 100:
                change = {
                    "type": "source_star",
                    "description": (
                        f"Source '{name}' is a star performer: "
                        f"{total_opps} opportunities, avg score {mean_score:.0f}"
                    ),
                    "action": "increase_frequency"
                }
                changes.append(change)

        return changes

    def _calibrate_scoring(self) -> list:
        """
        If operator has provided feedback (ratings on opportunities),
        use it to detect scoring dimension biases.
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
            our_score = opp.get('weighted_total', 0)

            # Map operator 1-5 to expected tiers
            if operator_rating >= 5 and our_tier in ['LOW', 'MEDIUM']:
                under_scored.append(opp)
            elif operator_rating <= 2 and our_tier in ['FIRE', 'HIGH']:
                over_scored.append(opp)

        if over_scored:
            # Find which dimensions are consistently over-rated
            over_dims = self._find_biased_dimensions(over_scored, 'over')
            if over_dims:
                change = {
                    "type": "scoring_calibration",
                    "description": (
                        f"Scoring tends to OVER-rate these dimensions: "
                        f"{', '.join(over_dims)}. Consider reducing their weights "
                        f"or tightening score criteria. Based on {len(over_scored)} "
                        f"over-scored opportunities."
                    ),
                    "action": "adjust_weights_down"
                }
                changes.append(change)
                self.kb.log_evolution(
                    "weight_adjustment", change["description"],
                    old_value=json.dumps(over_dims),
                    reasoning="Operator feedback indicates over-scoring"
                )

        if under_scored:
            under_dims = self._find_biased_dimensions(under_scored, 'under')
            if under_dims:
                change = {
                    "type": "scoring_calibration",
                    "description": (
                        f"Scoring tends to UNDER-rate these dimensions: "
                        f"{', '.join(under_dims)}. Consider increasing their weights. "
                        f"Based on {len(under_scored)} under-scored opportunities."
                    ),
                    "action": "adjust_weights_up"
                }
                changes.append(change)

        return changes

    def _detect_patterns(self) -> list:
        """
        Look for meta-patterns across all opportunities.
        What themes keep appearing? What's rising vs declining?
        """
        changes = []

        # Get all recent opportunities
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
            if sector_counts[top_sector] >= 3:
                change = {
                    "type": "pattern_detected",
                    "description": (
                        f"Pattern: '{top_sector}' sector appeared in "
                        f"{sector_counts[top_sector]}/{len(recent)} opportunities "
                        f"this week. This cluster may indicate a trending opportunity area."
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

    def _identify_blind_spots(self) -> list:
        """
        Check if certain operator capabilities are underexploited.
        If we have capabilities that aren't being matched to opportunities,
        we should scan harder in those areas.
        """
        changes = []

        recent = self.kb.get_recent_opportunities(hours=720)  # Last 30 days
        if not recent:
            return changes

        # Check which operator capability tags appear in opportunities
        all_tags = set()
        for opp in recent:
            all_tags.update(opp.get('tags', []))

        # Known capability areas that should generate opportunities
        capability_tags = {
            'fire-doors': 'Fire door expertise is underutilized',
            'coil-coating': 'Coil coating facility capability is underutilized',
            'it-infrastructure': 'IT infrastructure expertise is underutilized',
            'n8n-automation': 'n8n automation consulting potential is underutilized',
            'cross-border': 'Cross-border arbitrage opportunities are underexplored',
            'bim': 'BIM/Scan-to-BIM capability is underexplored',
            'scan-to-bim': 'Scan-to-BIM service opportunity is underexplored',
            'digital-twin': 'Digital twin / golden thread opportunity is underexplored',
            'revit': 'Revit/BIM modeling service opportunity is underexplored',
            'point-cloud': 'Point cloud processing / 3D scanning opportunity is underexplored',
        }

        for tag, message in capability_tags.items():
            matching = [t for t in all_tags if tag in t.lower()]
            if not matching:
                change = {
                    "type": "blind_spot",
                    "description": f"Blind spot detected: {message}. "
                                   f"Add more sources targeting this capability area.",
                    "action": "add_sources"
                }
                changes.append(change)

        return changes

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

        # Find dimensions with consistently high (over) or low (under) scores
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
                        'source_review': '🔍',
                        'source_error': '⚠️',
                        'source_star': '⭐',
                        'scoring_calibration': '⚖️',
                        'pattern_detected': '🔮',
                        'blind_spot': '👁️',
                    }.get(change.get('type', ''), '📝')
                    f.write(f"- {emoji} **{change.get('type', 'unknown')}**: "
                           f"{change.get('description', '')}\n")
            else:
                f.write("- No changes this cycle. System performing well.\n")
            f.write("\n---\n")
