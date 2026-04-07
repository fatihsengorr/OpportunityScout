"""
OpportunityScout — Scoring Utilities (DRY)

Centralized scoring logic used by all discovery engines:
- opportunity_scorer.py
- serendipity_engine.py
- model_generator.py
- localization_scanner.py
- capability_explorer.py (new)

Eliminates duplicated _calculate_weighted_total() and _determine_tier() methods.
"""

import logging

logger = logging.getLogger(__name__)

# ─── Default Weights & Thresholds ──────────────────────────────

DEFAULT_WEIGHTS = {
    # founder_fit is NOT here — it's used as a multiplier, not additive weight
    'ai_unlock': 2.5,
    'time_to_revenue': 2.5,
    'capital_efficiency': 2.0,
    'market_timing': 2.0,
    'defensibility': 1.5,
    'scale_potential': 1.5,
    'geographic_leverage': 1.5,
    'competition_gap': 1.0,
    'simplicity': 1.0
}

DEFAULT_TIERS = {
    'fire': 125,
    'high': 100,
    'medium': 75
}

# Maximum possible score: 10 * sum(weights) = 10 * 15.5 = 155, × 1.0 founder_fit = 155
MAX_SCORE = 155.0

SCORING_DIMENSIONS = list(DEFAULT_WEIGHTS.keys())


def calculate_weighted_total(scores: dict, config: dict = None) -> float:
    """
    Calculate weighted total from dimension scores.
    Founder Fit is applied as a MULTIPLIER (fit/10) on the base total,
    not as an additive weighted dimension.

    Args:
        scores: Dict of dimension scores. Each value can be:
            - dict with 'score' key: {"score": 8, "reason": "..."}
            - int/float: raw score value
        config: Optional config dict with scoring.weights override

    Returns:
        Weighted total score (0.0 - 155.0)
    """
    if config:
        weights = config.get('scoring', {}).get('weights', DEFAULT_WEIGHTS)
    else:
        weights = DEFAULT_WEIGHTS

    # Extract founder_fit as multiplier
    ff_data = scores.get('founder_fit', {})
    if isinstance(ff_data, dict):
        founder_fit = ff_data.get('score', 5)
    elif isinstance(ff_data, (int, float)):
        founder_fit = ff_data
    else:
        founder_fit = 5
    founder_fit = max(0, min(10, founder_fit))
    fit_multiplier = founder_fit / 10.0

    # Calculate base total from remaining 9 dimensions
    base_total = 0.0
    for dim, weight in weights.items():
        if dim == 'founder_fit':
            continue  # Skip — handled as multiplier
        score_data = scores.get(dim, {})
        if isinstance(score_data, dict):
            score = score_data.get('score', 0)
        elif isinstance(score_data, (int, float)):
            score = score_data
        else:
            score = 0
        score = max(0, min(10, score))
        base_total += score * weight

    # Apply founder fit multiplier
    total = base_total * fit_multiplier
    return round(total, 1)


def determine_tier(weighted_total: float, config: dict = None) -> str:
    """
    Determine opportunity tier from weighted total.

    Args:
        weighted_total: The calculated weighted score
        config: Optional config dict with scoring.tiers override

    Returns:
        Tier string: 'FIRE', 'HIGH', 'MEDIUM', or 'LOW'
    """
    if config:
        thresholds = config.get('scoring', {}).get('tiers', DEFAULT_TIERS)
    else:
        thresholds = DEFAULT_TIERS

    if weighted_total >= thresholds.get('fire', 125):
        return 'FIRE'
    elif weighted_total >= thresholds.get('high', 100):
        return 'HIGH'
    elif weighted_total >= thresholds.get('medium', 75):
        return 'MEDIUM'
    return 'LOW'


def score_and_tier(scores: dict, config: dict = None) -> tuple:
    """
    Convenience: calculate weighted total AND determine tier in one call.

    Returns:
        (weighted_total, tier) tuple
    """
    total = calculate_weighted_total(scores, config)
    tier = determine_tier(total, config)
    return total, tier


def validate_scores(scores: dict) -> dict:
    """
    Validate and normalize a scores dict. Ensures all dimensions present
    with valid score values. Used to sanitize Claude API responses.

    Returns:
        Cleaned scores dict with all dimensions present.
    """
    cleaned = {}
    for dim in SCORING_DIMENSIONS:
        score_data = scores.get(dim, {})
        if isinstance(score_data, dict):
            score = score_data.get('score', 0)
            reason = score_data.get('reason', 'No reason provided')
        elif isinstance(score_data, (int, float)):
            score = score_data
            reason = 'Score provided without reason'
        else:
            score = 0
            reason = 'Missing dimension'

        # Clamp to valid range
        score = max(0, min(10, int(score) if isinstance(score, float) and score == int(score) else score))

        cleaned[dim] = {
            'score': score,
            'reason': reason
        }

    return cleaned


def format_score_summary(scores: dict, weighted_total: float, tier: str) -> str:
    """
    Format a human-readable score summary for logging/display.
    """
    # Extract founder fit
    ff_data = scores.get('founder_fit', {})
    ff_score = ff_data.get('score', 5) if isinstance(ff_data, dict) else (ff_data if isinstance(ff_data, (int, float)) else 5)

    lines = [f"  Weighted Total: {weighted_total}/155 → {tier}"]
    lines.append(f"  founder_fit: {ff_score}/10 (MULTIPLIER: ×{ff_score/10:.1f})")
    for dim in SCORING_DIMENSIONS:
        if dim == 'founder_fit':
            continue
        score_data = scores.get(dim, {})
        if isinstance(score_data, dict):
            score = score_data.get('score', 0)
        elif isinstance(score_data, (int, float)):
            score = score_data
        else:
            score = 0
        weight = DEFAULT_WEIGHTS.get(dim, 1.0)
        lines.append(f"  {dim}: {score}/10 (×{weight} = {score * weight})")
    return "\n".join(lines)
