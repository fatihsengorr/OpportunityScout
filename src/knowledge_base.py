"""
OpportunityScout — Knowledge Base (SQLite Persistence Layer)

Stores all discovered opportunities, signals, source performance metrics,
evolution logs, and operator feedback. This is the long-term memory of the scout.
"""

import sqlite3
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional


class KnowledgeBase:
    """Persistent storage for OpportunityScout intelligence."""

    def __init__(self, db_path: str = "./data/opportunity_scout.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema."""
        cursor = self.conn.cursor()
        cursor.executescript("""
            -- Core opportunities table
            CREATE TABLE IF NOT EXISTS opportunities (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                one_liner TEXT,
                source TEXT,
                source_date TEXT,
                sector TEXT,
                geography TEXT,
                scores_json TEXT,          -- Full scoring breakdown as JSON
                weighted_total REAL,
                tier TEXT,                 -- FIRE, HIGH, MEDIUM, LOW
                why_now TEXT,
                first_move TEXT,
                revenue_path TEXT,
                risks_json TEXT,           -- List of risks as JSON
                connections_json TEXT,      -- Related opportunity IDs as JSON
                tags_json TEXT,            -- Tags as JSON array
                status TEXT DEFAULT 'new', -- new, reviewed, acted_on, archived, dead
                operator_rating INTEGER,   -- 1-5 feedback from operator
                operator_notes TEXT,
                deep_dive_json TEXT,        -- Full deep dive analysis if performed
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            -- Signals table (market signals that may or may not become opportunities)
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,                 -- regulatory, market, competitor, technology, social
                summary TEXT NOT NULL,
                source TEXT,
                source_date TEXT,
                relevance TEXT,
                potential_opportunities_json TEXT,
                tags_json TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Source performance tracking
            CREATE TABLE IF NOT EXISTS source_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                scan_date TEXT,
                items_found INTEGER DEFAULT 0,
                opportunities_generated INTEGER DEFAULT 0,
                avg_score REAL DEFAULT 0,
                highest_score REAL DEFAULT 0,
                errors INTEGER DEFAULT 0,
                scan_duration_seconds REAL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Evolution log (self-improvement tracking)
            CREATE TABLE IF NOT EXISTS evolution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_date TEXT,
                action_type TEXT,          -- weight_adjustment, source_added, source_removed, pattern_detected
                description TEXT,
                old_value TEXT,
                new_value TEXT,
                reasoning TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Cross-pollination insights
            CREATE TABLE IF NOT EXISTS cross_pollinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                insight TEXT NOT NULL,
                opportunity_ids_json TEXT,
                novel_angle TEXT,
                acted_on INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Scan history (what was scanned and when)
            CREATE TABLE IF NOT EXISTS scan_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_type TEXT,            -- daily, weekly, deep_dive, manual
                sources_scanned INTEGER,
                opportunities_found INTEGER,
                signals_found INTEGER,
                fire_alerts INTEGER DEFAULT 0,
                duration_seconds REAL,
                summary TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Operator feedback on scoring accuracy
            CREATE TABLE IF NOT EXISTS scoring_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT,
                dimension TEXT,
                original_score INTEGER,
                corrected_score INTEGER,
                feedback_note TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (opportunity_id) REFERENCES opportunities(id)
            );

            -- Trend tracking
            CREATE TABLE IF NOT EXISTS tracked_trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                first_seen TEXT,
                mention_count INTEGER DEFAULT 1,
                latest_mention TEXT,
                sources_json TEXT,
                trajectory TEXT DEFAULT 'stable', -- rising, stable, declining
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            -- Generated business models (creative synthesis output)
            CREATE TABLE IF NOT EXISTS generated_models (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                one_liner TEXT,
                origin_story TEXT,         -- What signals led to this idea
                problem TEXT,
                solution TEXT,
                ai_unlock TEXT,
                customer_json TEXT,
                business_model_json TEXT,
                founder_edge TEXT,
                competitive_landscape TEXT,
                first_move TEXT,
                week_1_plan TEXT,
                kill_criteria TEXT,
                sector TEXT,
                geography TEXT,
                tags_json TEXT,
                confidence TEXT,           -- HIGH, MEDIUM, LOW
                confidence_reasoning TEXT,
                validation_json TEXT,       -- Web validation results
                weighted_total REAL,
                tier TEXT,
                operator_rating INTEGER,   -- 1-5 feedback
                operator_notes TEXT,
                status TEXT DEFAULT 'new', -- new, exploring, building, killed, archived
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            -- ═══ Intelligence Mesh Tables (v2) ═══════════════════

            -- Intelligence events (event bus persistence)
            CREATE TABLE IF NOT EXISTS intelligence_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                data_json TEXT,
                source_module TEXT,
                processed INTEGER DEFAULT 0,
                processed_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Capability explorations (capability-first discovery tracking)
            CREATE TABLE IF NOT EXISTS capability_explorations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capability TEXT NOT NULL,
                industry TEXT NOT NULL,
                opportunities_found INTEGER DEFAULT 0,
                negative_evidence TEXT,
                best_score REAL DEFAULT 0,
                exploration_notes TEXT,
                next_exploration_date TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Regulatory deadlines (temporal intelligence)
            CREATE TABLE IF NOT EXISTS regulatory_deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                deadline_date TEXT NOT NULL,
                jurisdiction TEXT,            -- UK, EU, US, TR, UAE
                capabilities_json TEXT,       -- Which founder capabilities are relevant
                impact TEXT,                  -- Description of market impact
                search_queries_json TEXT,     -- Suggested search queries
                status TEXT DEFAULT 'active', -- active, passed, cancelled
                last_checked TEXT,
                alert_sent_180d INTEGER DEFAULT 0,
                alert_sent_90d INTEGER DEFAULT 0,
                alert_sent_30d INTEGER DEFAULT 0,
                alert_sent_7d INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            -- Tracked competitors (competitive intelligence)
            CREATE TABLE IF NOT EXISTS tracked_competitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                sector TEXT,
                related_opportunity_ids_json TEXT,
                website TEXT,
                latest_intel TEXT,
                funding_info TEXT,
                status TEXT DEFAULT 'active', -- active, acquired, closed, pivoted
                last_checked TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            -- Strategy performance (shared by serendipity 4-strategy, localization 5-strategy, generator 3-lens)
            CREATE TABLE IF NOT EXISTS strategy_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine TEXT NOT NULL,          -- 'serendipity', 'localization', 'generator'
                strategy_name TEXT NOT NULL,
                run_date TEXT,
                opportunities_found INTEGER DEFAULT 0,
                avg_score REAL DEFAULT 0,
                best_score REAL DEFAULT 0,
                fire_count INTEGER DEFAULT 0,
                high_count INTEGER DEFAULT 0,
                operator_acted_on INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0,
                duration_seconds REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Horizon Scanner frontiers (self-expanding discovery)
            CREATE TABLE IF NOT EXISTS horizon_frontiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frontier_name TEXT NOT NULL,
                frontier_type TEXT,           -- sector, buyer_persona, technology, regulation
                discovered_by_lens TEXT,
                search_queries_json TEXT,
                times_explored INTEGER DEFAULT 0,
                opportunities_found INTEGER DEFAULT 0,
                best_score REAL DEFAULT 0,
                status TEXT DEFAULT 'pending', -- pending, explored, productive, exhausted
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            -- Indexes for fast queries
            CREATE INDEX IF NOT EXISTS idx_horizon_status ON horizon_frontiers(status);
            CREATE INDEX IF NOT EXISTS idx_opp_tier ON opportunities(tier);
            CREATE INDEX IF NOT EXISTS idx_opp_status ON opportunities(status);
            CREATE INDEX IF NOT EXISTS idx_opp_score ON opportunities(weighted_total DESC);
            CREATE INDEX IF NOT EXISTS idx_opp_created ON opportunities(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(type);
            CREATE INDEX IF NOT EXISTS idx_source_metrics_name ON source_metrics(source_name);
            CREATE INDEX IF NOT EXISTS idx_trends_keyword ON tracked_trends(keyword);
            CREATE INDEX IF NOT EXISTS idx_events_type ON intelligence_events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_processed ON intelligence_events(processed);
            CREATE INDEX IF NOT EXISTS idx_cap_explore ON capability_explorations(capability, industry);
            CREATE INDEX IF NOT EXISTS idx_deadlines_date ON regulatory_deadlines(deadline_date);
            CREATE INDEX IF NOT EXISTS idx_strategy_perf ON strategy_performance(engine, strategy_name);
        """)
        self.conn.commit()

        # Schema migrations (safe to run repeatedly)
        self._migrate_schema()

    def _migrate_schema(self):
        """Run safe ALTER TABLE migrations for new columns."""
        cursor = self.conn.cursor()
        # Check if action_by column exists
        cursor.execute("PRAGMA table_info(opportunities)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'action_by' not in columns:
            cursor.execute("ALTER TABLE opportunities ADD COLUMN action_by TEXT")
            self.conn.commit()

        # Pipeline tracking — granular stages
        # Stages: discovered → researching → validating → building → launched → won/dead
        if 'pipeline_stage' not in columns:
            cursor.execute("""
                ALTER TABLE opportunities
                ADD COLUMN pipeline_stage TEXT DEFAULT 'discovered'
            """)
            self.conn.commit()
        if 'pipeline_notes' not in columns:
            cursor.execute("ALTER TABLE opportunities ADD COLUMN pipeline_notes TEXT")
            self.conn.commit()
        if 'pipeline_updated_at' not in columns:
            cursor.execute("ALTER TABLE opportunities ADD COLUMN pipeline_updated_at TEXT")
            self.conn.commit()

        # Deduplicate regulatory_deadlines and add unique index
        try:
            cursor.execute("""
                DELETE FROM regulatory_deadlines
                WHERE id NOT IN (
                    SELECT MIN(id) FROM regulatory_deadlines
                    GROUP BY name, deadline_date
                )
            """)
            if cursor.rowcount > 0:
                logger.info(f"🗑️ Removed {cursor.rowcount} duplicate deadline rows")
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_deadlines_unique
                ON regulatory_deadlines(name, deadline_date)
            """)
            self.conn.commit()
        except Exception:
            pass  # Index already exists or table doesn't exist yet

    # ─── Opportunity CRUD ───────────────────────────────────

    def save_opportunity(self, opp: dict) -> str:
        """Save an opportunity with guaranteed unique ID. Returns the opportunity ID."""
        # ALWAYS generate a unique ID — never trust Claude-generated IDs
        # Claude often reuses IDs like OPP-20260407-001 across multiple opportunities
        opp['id'] = f"OPP-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO opportunities
            (id, title, one_liner, source, source_date, sector, geography,
             scores_json, weighted_total, tier, why_now, first_move, revenue_path,
             risks_json, connections_json, tags_json, action_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            opp['id'], opp['title'], opp.get('one_liner', ''),
            opp.get('source', ''), opp.get('source_date', ''),
            opp.get('sector', ''), opp.get('geography', ''),
            json.dumps(opp.get('scores', {})),
            opp.get('weighted_total', 0),
            opp.get('tier', 'LOW'),
            opp.get('why_now', ''), opp.get('first_move', ''),
            opp.get('revenue_path', ''),
            json.dumps(opp.get('risks', [])),
            json.dumps(opp.get('connections', [])),
            json.dumps(opp.get('tags', [])),
            opp.get('action_by')
        ))
        self.conn.commit()
        return opp['id']

    def get_opportunity(self, opp_id: str) -> Optional[dict]:
        """Get a single opportunity by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_opportunity(row)
        return None

    def get_top_opportunities(self, limit: int = 20, tier: str = None,
                               status: str = None) -> list:
        """Get top-scoring opportunities with optional filters."""
        query = "SELECT * FROM opportunities WHERE 1=1"
        params = []
        if tier:
            query += " AND tier = ?"
            params.append(tier)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY weighted_total DESC LIMIT ?"
        params.append(limit)
        
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return [self._row_to_opportunity(row) for row in cursor.fetchall()]

    def get_recent_opportunities(self, hours: int = 24) -> list:
        """Get opportunities discovered in the last N hours."""
        cursor = self.conn.cursor()
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        cursor.execute(
            "SELECT * FROM opportunities WHERE created_at > ? ORDER BY weighted_total DESC",
            (since,)
        )
        return [self._row_to_opportunity(row) for row in cursor.fetchall()]

    def update_opportunity_status(self, opp_id: str, status: str,
                                   rating: int = None, notes: str = None):
        """Update opportunity status and optional feedback."""
        cursor = self.conn.cursor()
        updates = ["status = ?", "updated_at = datetime('now')"]
        params = [status]
        if rating is not None:
            updates.append("operator_rating = ?")
            params.append(rating)
        if notes:
            updates.append("operator_notes = ?")
            params.append(notes)
        params.append(opp_id)
        cursor.execute(
            f"UPDATE opportunities SET {', '.join(updates)} WHERE id = ?",
            params
        )
        self.conn.commit()

    # ─── Pipeline Tracking ──────────────────────────────────

    PIPELINE_STAGES = [
        'discovered',   # Just found — not yet reviewed
        'researching',  # Doing deep research, reading rivals
        'validating',   # Customer discovery calls, landing pages
        'building',     # Actually building MVP
        'launched',     # Live, seeking customers
        'won',          # Validated, generating revenue
        'dead',         # Killed — won't pursue
    ]

    def move_pipeline_stage(self, opp_id: str, stage: str,
                            append_note: str = None) -> bool:
        """Move opportunity to a new pipeline stage.

        Returns True if moved, False if stage invalid or opp not found.
        """
        if stage not in self.PIPELINE_STAGES:
            return False
        cursor = self.conn.cursor()
        # Check opportunity exists
        cursor.execute("SELECT pipeline_notes FROM opportunities WHERE id = ?",
                       (opp_id,))
        row = cursor.fetchone()
        if not row:
            return False

        # Append to notes if provided
        existing_notes = row['pipeline_notes'] or ''
        if append_note:
            from datetime import datetime as _dt
            ts = _dt.utcnow().strftime('%Y-%m-%d %H:%M')
            new_line = f"[{ts} → {stage}] {append_note}"
            new_notes = existing_notes + '\n' + new_line if existing_notes else new_line
        else:
            new_notes = existing_notes

        cursor.execute("""
            UPDATE opportunities
            SET pipeline_stage = ?,
                pipeline_notes = ?,
                pipeline_updated_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = ?
        """, (stage, new_notes, opp_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_pipeline_opportunities(self, stage: str = None,
                                    exclude_dead: bool = True) -> list:
        """Get opportunities grouped by pipeline stage.

        If stage is None, returns all active pipeline items.
        """
        cursor = self.conn.cursor()
        where_clauses = []
        params = []
        if stage:
            where_clauses.append("pipeline_stage = ?")
            params.append(stage)
        if exclude_dead:
            where_clauses.append("pipeline_stage != 'dead'")
            # Also filter out items still in 'discovered' that are not FIRE/HIGH
            # (they're basically just the queue — noisy)

        where = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        cursor.execute(f"""
            SELECT id, title, sector, tier, weighted_total, pipeline_stage,
                   pipeline_notes, pipeline_updated_at, action_by, created_at
            FROM opportunities
            {where}
            ORDER BY
              CASE pipeline_stage
                WHEN 'won' THEN 1
                WHEN 'launched' THEN 2
                WHEN 'building' THEN 3
                WHEN 'validating' THEN 4
                WHEN 'researching' THEN 5
                WHEN 'discovered' THEN 6
                WHEN 'dead' THEN 7
                ELSE 8
              END,
              weighted_total DESC
        """, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_pipeline_summary(self) -> dict:
        """Count opportunities per pipeline stage."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT pipeline_stage, COUNT(*) as cnt
            FROM opportunities
            GROUP BY pipeline_stage
        """)
        return {row['pipeline_stage'] or 'discovered': row['cnt']
                for row in cursor.fetchall()}

    def add_pipeline_note(self, opp_id: str, note: str) -> bool:
        """Append a timestamped note to an opportunity without changing stage."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT pipeline_notes, pipeline_stage FROM opportunities WHERE id = ?",
                       (opp_id,))
        row = cursor.fetchone()
        if not row:
            return False
        from datetime import datetime as _dt
        ts = _dt.utcnow().strftime('%Y-%m-%d %H:%M')
        stage = row['pipeline_stage'] or 'discovered'
        new_line = f"[{ts} | {stage}] {note}"
        existing = row['pipeline_notes'] or ''
        new_notes = existing + '\n' + new_line if existing else new_line
        cursor.execute("""
            UPDATE opportunities
            SET pipeline_notes = ?,
                updated_at = datetime('now')
            WHERE id = ?
        """, (new_notes, opp_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def is_duplicate(self, title: str, source: str = None,
                     sector: str = None, tags: list = None) -> bool:
        """
        Check if a similar opportunity already exists.
        Layer 1: Exact title match
        Layer 2: Keyword overlap in title
        Layer 3: Theme-level dedup (same sector + high tag overlap in last 30 days)
        """
        cursor = self.conn.cursor()

        # Layer 1: Exact title match
        cursor.execute("SELECT COUNT(*) FROM opportunities WHERE title = ?", (title,))
        if cursor.fetchone()[0] > 0:
            return True

        # Layer 2: Keyword overlap — extract significant words, check for matches
        keywords = [w.lower() for w in title.split() if len(w) > 3]
        if keywords:
            conditions = " AND ".join(["LOWER(title) LIKE ?" for _ in keywords[:4]])
            params = [f"%{kw}%" for kw in keywords[:4]]
            if conditions:
                cursor.execute(
                    f"SELECT COUNT(*) FROM opportunities WHERE {conditions}",
                    params
                )
                if cursor.fetchone()[0] > 0:
                    return True

        # Layer 3: Theme-level dedup — same sector + high tag overlap (last 30 days)
        if sector and tags and isinstance(tags, list) and len(tags) >= 2:
            new_tags = set(t.lower() for t in tags)
            cursor.execute(
                "SELECT tags_json FROM opportunities "
                "WHERE sector = ? AND created_at > datetime('now', '-30 days')",
                (sector,)
            )
            for row in cursor.fetchall():
                try:
                    existing_tags = set(t.lower() for t in json.loads(row[0] or '[]'))
                except (json.JSONDecodeError, TypeError):
                    continue
                if not existing_tags:
                    continue
                # Jaccard similarity
                intersection = new_tags & existing_tags
                union = new_tags | existing_tags
                if union and len(intersection) / len(union) >= 0.5:
                    return True

        return False

    # ─── Signal CRUD ────────────────────────────────────────

    def save_signal(self, signal: dict) -> int:
        """Save a market signal. Returns the signal ID."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO signals (type, summary, source, source_date, relevance,
                                potential_opportunities_json, tags_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            signal.get('type', 'market'),
            signal['summary'],
            signal.get('source', ''),
            signal.get('source_date', ''),
            signal.get('relevance', ''),
            json.dumps(signal.get('potential_opportunities', [])),
            json.dumps(signal.get('tags', []))
        ))
        self.conn.commit()
        return cursor.lastrowid

    # ─── Source Metrics ─────────────────────────────────────

    def log_source_scan(self, source_name: str, items_found: int,
                        opportunities: int, avg_score: float,
                        highest_score: float, errors: int,
                        duration: float):
        """Log a source scan result for performance tracking."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO source_metrics 
            (source_name, scan_date, items_found, opportunities_generated,
             avg_score, highest_score, errors, scan_duration_seconds)
            VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?)
        """, (source_name, items_found, opportunities, avg_score,
              highest_score, errors, duration))
        self.conn.commit()

    def get_source_performance(self, days: int = 30) -> list:
        """Get aggregated source performance over the last N days."""
        cursor = self.conn.cursor()
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        cursor.execute("""
            SELECT source_name,
                   COUNT(*) as scan_count,
                   SUM(items_found) as total_items,
                   SUM(opportunities_generated) as total_opportunities,
                   AVG(avg_score) as mean_score,
                   MAX(highest_score) as best_score,
                   SUM(errors) as total_errors
            FROM source_metrics
            WHERE created_at > ?
            GROUP BY source_name
            ORDER BY total_opportunities DESC
        """, (since,))
        return [dict(row) for row in cursor.fetchall()]

    # ─── Evolution Log ──────────────────────────────────────

    def log_evolution(self, action_type: str, description: str,
                      old_value: str = None, new_value: str = None,
                      reasoning: str = None):
        """Log a self-improvement action."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO evolution_log (cycle_date, action_type, description,
                                       old_value, new_value, reasoning)
            VALUES (datetime('now'), ?, ?, ?, ?, ?)
        """, (action_type, description, old_value, new_value, reasoning))
        self.conn.commit()

    # ─── Cross-Pollination ──────────────────────────────────

    def save_cross_pollination(self, insight: str, opp_ids: list,
                                novel_angle: str):
        """Save a cross-pollination insight."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO cross_pollinations (insight, opportunity_ids_json, novel_angle)
            VALUES (?, ?, ?)
        """, (insight, json.dumps(opp_ids), novel_angle))
        self.conn.commit()

    # ─── Scan History ───────────────────────────────────────

    def log_scan(self, scan_type: str, sources_scanned: int,
                 opportunities_found: int, signals_found: int,
                 fire_alerts: int, duration: float, summary: str):
        """Log a completed scan cycle."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO scan_history 
            (scan_type, sources_scanned, opportunities_found, signals_found,
             fire_alerts, duration_seconds, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (scan_type, sources_scanned, opportunities_found,
              signals_found, fire_alerts, duration, summary))
        self.conn.commit()

    # ─── Trends ─────────────────────────────────────────────

    def track_trend(self, keyword: str, source: str):
        """Track or update a trend keyword."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tracked_trends WHERE keyword = ?", (keyword,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
                UPDATE tracked_trends 
                SET mention_count = mention_count + 1,
                    latest_mention = datetime('now'),
                    sources_json = ?,
                    updated_at = datetime('now')
                WHERE keyword = ?
            """, (
                json.dumps(list(set(
                    json.loads(existing['sources_json'] or '[]') + [source]
                ))),
                keyword
            ))
        else:
            cursor.execute("""
                INSERT INTO tracked_trends (keyword, first_seen, latest_mention, sources_json)
                VALUES (?, datetime('now'), datetime('now'), ?)
            """, (keyword, json.dumps([source])))
        self.conn.commit()

    # ─── Statistics ─────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get overall knowledge base statistics."""
        cursor = self.conn.cursor()
        stats = {}
        for table, key in [('opportunities', 'total_opportunities'),
                           ('signals', 'total_signals'),
                           ('scan_history', 'total_scans'),
                           ('evolution_log', 'total_evolutions')]:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            stats[key] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM opportunities WHERE tier = 'FIRE'")
        stats['fire_opportunities'] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM opportunities WHERE tier = 'HIGH'")
        stats['high_opportunities'] = cursor.fetchone()[0]
        cursor.execute(
            "SELECT AVG(weighted_total) FROM opportunities WHERE weighted_total > 0"
        )
        result = cursor.fetchone()[0]
        stats['avg_score'] = round(result, 1) if result else 0
        return stats

    # ─── Intelligence Events (Event Bus) ───────────────────

    def save_event(self, event: dict):
        """Persist an intelligence event."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO intelligence_events (event_type, data_json, source_module)
            VALUES (?, ?, ?)
        """, (
            event['event_type'],
            json.dumps(event.get('data', {})),
            event.get('source_module', 'unknown')
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_unprocessed_events(self, event_type: str = None,
                                limit: int = 50) -> list:
        """Get unprocessed events, oldest first."""
        cursor = self.conn.cursor()
        query = "SELECT * FROM intelligence_events WHERE processed = 0"
        params = []
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)
        cursor.execute(query, params)
        events = []
        for row in cursor.fetchall():
            e = dict(row)
            e['data'] = json.loads(e.pop('data_json', '{}') or '{}')
            events.append(e)
        return events

    def mark_event_processed(self, event_id: int):
        """Mark an event as processed."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE intelligence_events
            SET processed = 1, processed_at = datetime('now')
            WHERE id = ?
        """, (event_id,))
        self.conn.commit()

    def get_recent_events(self, hours: int = 24,
                          event_type: str = None) -> list:
        """Get recent events for context building."""
        cursor = self.conn.cursor()
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        query = "SELECT * FROM intelligence_events WHERE created_at > ?"
        params = [since]
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        events = []
        for row in cursor.fetchall():
            e = dict(row)
            e['data'] = json.loads(e.pop('data_json', '{}') or '{}')
            events.append(e)
        return events

    def get_event_stats(self) -> dict:
        """Get event statistics for health dashboard."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM intelligence_events")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM intelligence_events WHERE processed = 0")
        unprocessed = cursor.fetchone()[0]
        cursor.execute("""
            SELECT event_type, COUNT(*) as count
            FROM intelligence_events
            GROUP BY event_type
        """)
        by_type = {row['event_type']: row['count'] for row in cursor.fetchall()}
        return {
            'total_events': total,
            'unprocessed_events': unprocessed,
            'events_by_type': by_type
        }

    # ─── Capability Explorations ────────────────────────────

    def save_exploration(self, capability: str, industry: str,
                         opportunities_found: int = 0,
                         negative_evidence: str = None,
                         best_score: float = 0,
                         notes: str = None):
        """Log a capability exploration result."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO capability_explorations
            (capability, industry, opportunities_found, negative_evidence,
             best_score, exploration_notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (capability, industry, opportunities_found, negative_evidence,
              best_score, notes))
        self.conn.commit()

    def get_exploration_history(self, capability: str = None,
                                limit: int = 50) -> list:
        """Get exploration history, optionally filtered by capability."""
        cursor = self.conn.cursor()
        query = "SELECT * FROM capability_explorations"
        params = []
        if capability:
            query += " WHERE capability = ?"
            params.append(capability)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_least_explored_capability(self) -> Optional[str]:
        """Find the capability cluster with fewest explorations."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT capability, COUNT(*) as explore_count
            FROM capability_explorations
            GROUP BY capability
            ORDER BY explore_count ASC
            LIMIT 1
        """)
        row = cursor.fetchone()
        return row['capability'] if row else None

    # ─── Regulatory Deadlines ──────────────────────────────

    def save_deadline(self, name: str, deadline_date: str,
                      jurisdiction: str = None,
                      capabilities: list = None,
                      impact: str = None,
                      search_queries: list = None):
        """Save or update a regulatory deadline (upsert by name+date)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO regulatory_deadlines
            (name, deadline_date, jurisdiction, capabilities_json,
             impact, search_queries_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name, deadline_date) DO UPDATE SET
                jurisdiction = excluded.jurisdiction,
                capabilities_json = excluded.capabilities_json,
                impact = excluded.impact,
                search_queries_json = excluded.search_queries_json,
                updated_at = datetime('now')
        """, (name, deadline_date, jurisdiction,
              json.dumps(capabilities or []),
              impact,
              json.dumps(search_queries or [])))
        self.conn.commit()

    def get_approaching_deadlines(self, days: int = 180) -> list:
        """Get deadlines approaching within N days."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM regulatory_deadlines
            WHERE status = 'active'
            AND date(deadline_date) <= date('now', '+' || ? || ' days')
            AND date(deadline_date) >= date('now')
            ORDER BY deadline_date ASC
        """, (days,))
        deadlines = []
        for row in cursor.fetchall():
            d = dict(row)
            d['capabilities'] = json.loads(d.pop('capabilities_json', '[]') or '[]')
            d['search_queries'] = json.loads(d.pop('search_queries_json', '[]') or '[]')
            deadlines.append(d)
        return deadlines

    # ─── Tracked Competitors ───────────────────────────────

    def save_competitor(self, company_name: str, sector: str = None,
                        related_opp_ids: list = None,
                        website: str = None, intel: str = None):
        """Save or update a tracked competitor."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO tracked_competitors
            (company_name, sector, related_opportunity_ids_json, website, latest_intel)
            VALUES (?, ?, ?, ?, ?)
        """, (company_name, sector,
              json.dumps(related_opp_ids or []),
              website, intel))
        self.conn.commit()

    def get_tracked_competitors(self, sector: str = None) -> list:
        """Get tracked competitors, optionally filtered by sector."""
        cursor = self.conn.cursor()
        query = "SELECT * FROM tracked_competitors WHERE status = 'active'"
        params = []
        if sector:
            query += " AND sector = ?"
            params.append(sector)
        query += " ORDER BY updated_at DESC"
        cursor.execute(query, params)
        competitors = []
        for row in cursor.fetchall():
            c = dict(row)
            c['related_opportunity_ids'] = json.loads(
                c.pop('related_opportunity_ids_json', '[]') or '[]'
            )
            competitors.append(c)
        return competitors

    # ─── Strategy Performance ──────────────────────────────

    def log_strategy_performance(self, engine: str, strategy_name: str,
                                  opportunities_found: int = 0,
                                  avg_score: float = 0,
                                  best_score: float = 0,
                                  fire_count: int = 0,
                                  high_count: int = 0,
                                  cost_usd: float = 0,
                                  duration_seconds: float = 0):
        """Log performance metrics for a discovery strategy."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO strategy_performance
            (engine, strategy_name, run_date, opportunities_found,
             avg_score, best_score, fire_count, high_count,
             cost_usd, duration_seconds)
            VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?)
        """, (engine, strategy_name, opportunities_found,
              avg_score, best_score, fire_count, high_count,
              cost_usd, duration_seconds))
        self.conn.commit()

    def get_strategy_performance(self, engine: str = None,
                                  days: int = 30) -> list:
        """Get strategy performance data for analysis."""
        cursor = self.conn.cursor()
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        query = """
            SELECT engine, strategy_name,
                   COUNT(*) as runs,
                   SUM(opportunities_found) as total_opps,
                   AVG(avg_score) as mean_avg_score,
                   MAX(best_score) as max_score,
                   SUM(fire_count) as total_fires,
                   SUM(high_count) as total_highs,
                   AVG(cost_usd) as avg_cost,
                   AVG(duration_seconds) as avg_duration
            FROM strategy_performance
            WHERE created_at > ?
        """
        params = [since]
        if engine:
            query += " AND engine = ?"
            params.append(engine)
        query += " GROUP BY engine, strategy_name ORDER BY total_fires DESC, max_score DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    # ─── Cross-Pollination (enhanced) ──────────────────────

    def get_recent_cross_pollinations(self, limit: int = 20) -> list:
        """Get recent cross-pollination insights."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM cross_pollinations
            ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d['opportunity_ids'] = json.loads(
                d.pop('opportunity_ids_json', '[]') or '[]'
            )
            results.append(d)
        return results

    def get_unacted_cross_pollinations(self) -> list:
        """Get cross-pollinations that haven't been acted on yet."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM cross_pollinations
            WHERE acted_on = 0
            ORDER BY created_at DESC
        """)
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d['opportunity_ids'] = json.loads(
                d.pop('opportunity_ids_json', '[]') or '[]'
            )
            results.append(d)
        return results

    # ─── Horizon Frontiers ──────────────────────────────────

    def save_frontier(self, frontier: dict) -> int:
        """Save a newly discovered frontier. Returns row ID."""
        cursor = self.conn.cursor()
        # Check if frontier already exists (by name)
        cursor.execute(
            "SELECT id FROM horizon_frontiers WHERE frontier_name = ?",
            (frontier['frontier_name'],)
        )
        if cursor.fetchone():
            return -1  # Already exists
        cursor.execute("""
            INSERT INTO horizon_frontiers
            (frontier_name, frontier_type, discovered_by_lens, search_queries_json)
            VALUES (?, ?, ?, ?)
        """, (
            frontier['frontier_name'],
            frontier.get('frontier_type', 'sector'),
            frontier.get('discovered_by_lens', ''),
            json.dumps(frontier.get('search_queries', []))
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_pending_frontiers(self, limit: int = 10) -> list:
        """Get frontiers waiting to be explored."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM horizon_frontiers
            WHERE status IN ('pending', 'explored')
            ORDER BY
                CASE status WHEN 'pending' THEN 0 ELSE 1 END,
                created_at ASC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def update_frontier_status(self, frontier_id: int, status: str,
                                opps_found: int = 0, best_score: float = 0):
        """Update frontier after exploration."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE horizon_frontiers SET
                status = ?,
                times_explored = times_explored + 1,
                opportunities_found = opportunities_found + ?,
                best_score = MAX(best_score, ?),
                updated_at = datetime('now')
            WHERE id = ?
        """, (status, opps_found, best_score, frontier_id))
        self.conn.commit()

    def get_known_sectors(self, limit: int = 100) -> list:
        """Get all distinct sectors from existing opportunities."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT sector FROM opportunities
            WHERE sector IS NOT NULL AND sector != ''
            ORDER BY sector LIMIT ?
        """, (limit,))
        return [row[0] for row in cursor.fetchall()]

    # ─── Helpers ────────────────────────────────────────────

    def _row_to_opportunity(self, row) -> dict:
        """Convert a database row to an opportunity dict."""
        d = dict(row)
        for json_field in ['scores_json', 'risks_json', 'connections_json', 'tags_json']:
            key = json_field.replace('_json', '')
            d[key] = json.loads(d.pop(json_field, '[]') or '[]')
        if 'deep_dive_json' in d and d['deep_dive_json']:
            d['deep_dive'] = json.loads(d.pop('deep_dive_json'))
        else:
            d.pop('deep_dive_json', None)
        return d

    def close(self):
        """Close database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
