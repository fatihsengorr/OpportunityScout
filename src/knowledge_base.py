"""
OpportunityScout — Knowledge Base (SQLite Persistence Layer)

Stores all discovered opportunities, signals, source performance metrics,
evolution logs, and operator feedback. This is the long-term memory of the scout.
"""

import sqlite3
import json
import os
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

            -- Indexes for fast queries
            CREATE INDEX IF NOT EXISTS idx_opp_tier ON opportunities(tier);
            CREATE INDEX IF NOT EXISTS idx_opp_status ON opportunities(status);
            CREATE INDEX IF NOT EXISTS idx_opp_score ON opportunities(weighted_total DESC);
            CREATE INDEX IF NOT EXISTS idx_opp_created ON opportunities(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(type);
            CREATE INDEX IF NOT EXISTS idx_source_metrics_name ON source_metrics(source_name);
            CREATE INDEX IF NOT EXISTS idx_trends_keyword ON tracked_trends(keyword);
        """)
        self.conn.commit()

    # ─── Opportunity CRUD ───────────────────────────────────

    def save_opportunity(self, opp: dict) -> str:
        """Save or update an opportunity. Returns the opportunity ID."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO opportunities 
            (id, title, one_liner, source, source_date, sector, geography,
             scores_json, weighted_total, tier, why_now, first_move, revenue_path,
             risks_json, connections_json, tags_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
            json.dumps(opp.get('tags', []))
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

    def is_duplicate(self, title: str, source: str = None) -> bool:
        """Check if a similar opportunity already exists."""
        cursor = self.conn.cursor()
        # Simple title similarity check — Claude does semantic dedup
        cursor.execute(
            "SELECT COUNT(*) FROM opportunities WHERE title = ? OR (source = ? AND source != '')",
            (title, source or '')
        )
        return cursor.fetchone()[0] > 0

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
