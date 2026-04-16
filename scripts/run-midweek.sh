#!/bin/bash
# OpportunityScout — Mid-week exploration pipeline
# Runs: Thursday 06:00 UTC via scout-midweek.timer
# Extra breadth scan between weekly deep dives
set -o pipefail

PROJECT=/opt/opportunity-scout
VENV=$PROJECT/venv/bin/python
cd "$PROJECT"
set -a; source .env; set +a

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [$1] $2"; }

run_step() {
    local name="$1"; shift
    log "START" "$name"
    local start=$(date +%s)
    "$VENV" "$@" 2>&1
    local rc=$?
    local elapsed=$(( $(date +%s) - start ))
    if [ $rc -eq 0 ]; then
        log "OK" "$name completed in ${elapsed}s"
    else
        log "FAIL" "$name failed (exit=$rc) after ${elapsed}s"
    fi
    return 0  # Always continue to next step
}

echo "========================================"
log "PIPELINE" "Mid-week exploration starting"
echo "========================================"

run_step "explore"       -m src.cli explore --count 3
run_step "horizon"       -m src.cli horizon --mode daily
run_step "serendipity"   -m src.cli serendipity --mode daily

echo "========================================"
log "PIPELINE" "Mid-week exploration complete"
echo "========================================"
