"""
OpportunityScout — Web Dashboard

Lightweight FastAPI + server-rendered HTML dashboard.
Read-only view into the SQLite knowledge base.

Routes:
  GET  /               — Top opportunities (card grid, filters)
  GET  /pipeline       — Kanban view of pipeline stages
  GET  /opp/{id}       — Single opportunity full detail
  GET  /analytics      — Trends, strategy performance, cost
  GET  /search         — Semantic search (hits Open Brain)
  POST /move/{id}      — Move pipeline stage (htmx)
  POST /note/{id}      — Add note (htmx)

Why not Next.js? SQLite is single-process, dashboard is single-user, no need
for a separate API layer. FastAPI + Jinja2 is ~15% of the code and runs
as a systemd service next to scout-telegram.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


BASE_DIR = Path(__file__).parent
DB_PATH = os.environ.get(
    "SCOUT_DB_PATH",
    str(Path(__file__).parent.parent / "data" / "opportunity_scout.db")
)

app = FastAPI(title="OpportunityScout Dashboard")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def get_db():
    """Return a new SQLite connection per request (thread-safe)."""
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


# ─── Helpers ────────────────────────────────────────────────

PIPELINE_STAGES = [
    'discovered', 'researching', 'validating',
    'building', 'launched', 'won', 'dead'
]

STAGE_EMOJI = {
    'discovered': '🔎',
    'researching': '📚',
    'validating': '🎯',
    'building': '🔨',
    'launched': '🚀',
    'won': '🏆',
    'dead': '💀',
}

TIER_EMOJI = {'FIRE': '🔥', 'HIGH': '⭐', 'MEDIUM': '📊', 'LOW': '📝'}


def row_to_dict(row):
    if not row:
        return None
    d = dict(row)
    # Parse JSON columns lazily
    for k in ('scores_json', 'risks_json', 'tags_json', 'connections_json',
              'action_kit_json', 'finance_json', 'validation_json',
              'consensus_json', 'deep_dive_json'):
        if d.get(k):
            try:
                d[k.replace('_json', '')] = json.loads(d[k])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


# ─── Routes ─────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request,
               tier: str = None, sector: str = None,
               limit: int = 40, days: int = 30):
    """Top opportunities grid with filters."""
    conn = get_db()
    cursor = conn.cursor()

    where = ["1=1"]
    params = []
    if tier and tier != 'all':
        where.append("tier = ?")
        params.append(tier.upper())
    if sector:
        where.append("sector LIKE ?")
        params.append(f"%{sector}%")
    if days:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        where.append("created_at >= ?")
        params.append(cutoff)

    where_sql = " AND ".join(where)
    cursor.execute(f"""
        SELECT * FROM opportunities
        WHERE {where_sql}
        ORDER BY weighted_total DESC, created_at DESC
        LIMIT ?
    """, params + [limit])

    opportunities = [row_to_dict(r) for r in cursor.fetchall()]

    # Stats
    cursor.execute(f"""
        SELECT tier, COUNT(*) as cnt FROM opportunities
        WHERE {where_sql}
        GROUP BY tier
    """, params)
    tier_counts = {r['tier']: r['cnt'] for r in cursor.fetchall()}

    cursor.execute(f"""
        SELECT sector, COUNT(*) as cnt FROM opportunities
        WHERE {where_sql}
        GROUP BY sector ORDER BY cnt DESC LIMIT 10
    """, params)
    sector_counts = [{'sector': r['sector'], 'count': r['cnt']}
                     for r in cursor.fetchall()]

    conn.close()

    return templates.TemplateResponse("home.html", {
        "request": request,
        "opportunities": opportunities,
        "tier_counts": tier_counts,
        "sector_counts": sector_counts,
        "filter_tier": tier or "all",
        "filter_sector": sector or "",
        "filter_days": days,
        "stage_emoji": STAGE_EMOJI,
        "tier_emoji": TIER_EMOJI,
    })


@app.get("/pipeline", response_class=HTMLResponse)
async def pipeline(request: Request):
    """Kanban view grouped by pipeline stage."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, sector, tier, weighted_total, pipeline_stage,
               pipeline_notes, pipeline_updated_at, action_by
        FROM opportunities
        WHERE tier IN ('FIRE', 'HIGH')
           OR pipeline_stage NOT IN ('discovered', 'dead')
        ORDER BY weighted_total DESC
    """)
    all_items = [dict(r) for r in cursor.fetchall()]

    # Group by stage
    by_stage = {s: [] for s in PIPELINE_STAGES}
    for item in all_items:
        stage = item.get('pipeline_stage') or 'discovered'
        if stage in by_stage:
            by_stage[stage].append(item)

    conn.close()

    return templates.TemplateResponse("pipeline.html", {
        "request": request,
        "by_stage": by_stage,
        "stages": PIPELINE_STAGES,
        "stage_emoji": STAGE_EMOJI,
        "tier_emoji": TIER_EMOJI,
    })


@app.get("/opp/{opp_id}", response_class=HTMLResponse)
async def opportunity_detail(request: Request, opp_id: str):
    """Full detail view for a single opportunity."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"{opp_id} not found")

    opp = row_to_dict(row)
    return templates.TemplateResponse("detail.html", {
        "request": request,
        "opp": opp,
        "stage_emoji": STAGE_EMOJI,
        "tier_emoji": TIER_EMOJI,
        "stages": PIPELINE_STAGES,
    })


@app.get("/analytics", response_class=HTMLResponse)
async def analytics(request: Request):
    """Trends, strategy performance, source performance."""
    conn = get_db()
    cursor = conn.cursor()

    # Daily discovery rate (last 30 days)
    cursor.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as cnt,
               SUM(CASE WHEN tier='FIRE' THEN 1 ELSE 0 END) as fires,
               SUM(CASE WHEN tier='HIGH' THEN 1 ELSE 0 END) as highs
        FROM opportunities
        WHERE created_at >= datetime('now', '-30 days')
        GROUP BY DATE(created_at)
        ORDER BY day DESC
    """)
    daily = [dict(r) for r in cursor.fetchall()]

    # Strategy performance
    cursor.execute("""
        SELECT engine, strategy_name,
               SUM(opportunities_found) as total,
               SUM(fire_count) as fires,
               AVG(avg_score) as avg_score,
               MAX(best_score) as best
        FROM strategy_performance
        WHERE run_date >= datetime('now', '-30 days')
        GROUP BY engine, strategy_name
        ORDER BY fires DESC, total DESC
    """)
    strategies = [dict(r) for r in cursor.fetchall()]

    # Source performance
    cursor.execute("""
        SELECT source_name,
               SUM(items_found) as items,
               SUM(opportunities_generated) as opps,
               AVG(avg_score) as avg_score
        FROM source_metrics
        WHERE scan_date >= datetime('now', '-30 days')
        GROUP BY source_name
        HAVING opps > 0
        ORDER BY opps DESC LIMIT 20
    """)
    sources = [dict(r) for r in cursor.fetchall()]

    # Disputed count
    cursor.execute("SELECT COUNT(*) as cnt FROM opportunities WHERE score_disputed = 1")
    disputed = cursor.fetchone()['cnt']

    conn.close()

    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "daily": daily,
        "strategies": strategies,
        "sources": sources,
        "disputed": disputed,
    })


@app.post("/move/{opp_id}")
async def move_stage(opp_id: str,
                     stage: str = Form(...),
                     note: str = Form(None)):
    """htmx-compatible stage move."""
    if stage not in PIPELINE_STAGES:
        raise HTTPException(status_code=400, detail="Invalid stage")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT pipeline_notes FROM opportunities WHERE id = ?", (opp_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404)

    existing = row['pipeline_notes'] or ''
    if note:
        ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        new_line = f"[{ts} → {stage}] {note}"
        new_notes = existing + '\n' + new_line if existing else new_line
    else:
        new_notes = existing

    cursor.execute("""
        UPDATE opportunities
        SET pipeline_stage = ?, pipeline_notes = ?,
            pipeline_updated_at = datetime('now'),
            updated_at = datetime('now')
        WHERE id = ?
    """, (stage, new_notes, opp_id))
    conn.commit()
    conn.close()

    return RedirectResponse(url=f"/opp/{opp_id}", status_code=303)


@app.post("/note/{opp_id}")
async def add_note(opp_id: str, note: str = Form(...)):
    """Add a timestamped note without changing stage."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT pipeline_notes, pipeline_stage FROM opportunities WHERE id = ?",
                   (opp_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404)

    ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
    stage = row['pipeline_stage'] or 'discovered'
    new_line = f"[{ts} | {stage}] {note}"
    existing = row['pipeline_notes'] or ''
    new_notes = existing + '\n' + new_line if existing else new_line

    cursor.execute("""
        UPDATE opportunities
        SET pipeline_notes = ?, updated_at = datetime('now')
        WHERE id = ?
    """, (new_notes, opp_id))
    conn.commit()
    conn.close()

    return RedirectResponse(url=f"/opp/{opp_id}", status_code=303)


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = ""):
    """Simple keyword search across opportunity titles/descriptions."""
    opportunities = []
    if q and len(q) >= 2:
        conn = get_db()
        cursor = conn.cursor()
        like = f"%{q}%"
        cursor.execute("""
            SELECT * FROM opportunities
            WHERE title LIKE ? OR one_liner LIKE ? OR description LIKE ?
               OR sector LIKE ? OR tags_json LIKE ?
            ORDER BY weighted_total DESC LIMIT 50
        """, (like, like, like, like, like))
        opportunities = [row_to_dict(r) for r in cursor.fetchall()]
        conn.close()

    return templates.TemplateResponse("search.html", {
        "request": request,
        "q": q,
        "opportunities": opportunities,
        "tier_emoji": TIER_EMOJI,
    })


@app.get("/api/stats", response_class=JSONResponse)
async def api_stats():
    """JSON stats endpoint for external dashboards / widgets."""
    conn = get_db()
    cursor = conn.cursor()
    stats = {}
    cursor.execute("SELECT COUNT(*) as cnt FROM opportunities")
    stats['total_opportunities'] = cursor.fetchone()['cnt']
    cursor.execute("""
        SELECT tier, COUNT(*) as cnt FROM opportunities GROUP BY tier
    """)
    stats['by_tier'] = {r['tier']: r['cnt'] for r in cursor.fetchall()}
    cursor.execute("""
        SELECT pipeline_stage, COUNT(*) as cnt FROM opportunities
        GROUP BY pipeline_stage
    """)
    stats['by_stage'] = {(r['pipeline_stage'] or 'discovered'): r['cnt']
                         for r in cursor.fetchall()}
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM opportunities
        WHERE created_at >= datetime('now', '-7 days')
    """)
    stats['last_7_days'] = cursor.fetchone()['cnt']
    conn.close()
    return stats


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("DASHBOARD_PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
