#!/bin/bash
# OpportunityScout — Daily scan pipeline
# Runs: every day 06:00 UTC via scout-daily.timer
# Each step runs independently — one failure won't block the rest
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
log "PIPELINE" "Daily scan starting"
echo "========================================"

run_step "scan-tier1"    -m src.cli scan --tier 1
run_step "serendipity"   -m src.cli serendipity --mode daily
run_step "horizon"       -m src.cli horizon --mode daily
run_step "explore"       -m src.cli explore --count 2
run_step "deadlines"     -m src.cli deadlines
run_step "digest"        -m src.cli digest

echo "========================================"
log "PIPELINE" "Daily scan complete"
echo "========================================"
