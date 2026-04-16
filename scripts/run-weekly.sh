#!/bin/bash
# OpportunityScout — Weekly deep scan pipeline
# Runs: Monday 03:00 UTC via scout-weekly.timer
# Full intelligence cycle with deep analysis (Opus model)
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

cooldown() {
    log "WAIT" "API cooldown ${1}s..."
    sleep "$1"
}

echo "========================================"
log "PIPELINE" "Weekly deep scan starting"
echo "========================================"

run_step "scan-tier2"        -m src.cli scan --tier 2
run_step "evolve"            -m src.cli evolve
run_step "generate"          -m src.cli generate --count 3

cooldown 120

run_step "serendipity-deep"  -m src.cli serendipity --mode deep

cooldown 120

run_step "horizon-deep"      -m src.cli horizon --mode deep

cooldown 120

run_step "localize"          -m src.cli localize --count 5
run_step "crosspoll"         -m src.cli crosspoll
run_step "competitors"       -m src.cli competitors
run_step "weekly-report"     -m src.cli weekly

echo "========================================"
log "PIPELINE" "Weekly deep scan complete"
echo "========================================"
