"""SQLite persistence layer for Percept."""

import json
import logging
import os
import sqlite3
from sqlite3 import IntegrityError
import threading
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


class PerceptDB:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "percept.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            c = self._conn
            c.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    date TEXT NOT NULL,
                    duration_seconds REAL,
                    segment_count INTEGER,
                    word_count INTEGER,
                    speakers TEXT,
                    topics TEXT,
                    transcript TEXT,
                    summary TEXT,
                    file_path TEXT,
                    summary_file_path TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                );
                CREATE TABLE IF NOT EXISTS speakers (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    first_seen REAL,
                    last_seen REAL,
                    total_words INTEGER DEFAULT 0,
                    total_segments INTEGER DEFAULT 0,
                    relationship TEXT,
                    voice_profile TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                );
                CREATE TABLE IF NOT EXISTS contacts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    relationship TEXT,
                    last_mentioned REAL,
                    mention_count INTEGER DEFAULT 0,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                );
                CREATE TABLE IF NOT EXISTS address_book_contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    first_name TEXT NOT NULL,
                    last_name TEXT,
                    alias TEXT,  -- nickname/shortname for voice matching
                    category TEXT DEFAULT 'personal',  -- 'family', 'business', 'personal'
                    phone TEXT,
                    email TEXT,
                    slack TEXT,  -- Slack handle or ID
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    conversation_id TEXT,
                    intent TEXT NOT NULL,
                    params TEXT,
                    raw_text TEXT,
                    status TEXT DEFAULT 'pending',
                    result TEXT,
                    executed_at REAL,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    keywords TEXT,
                    last_mentioned REAL,
                    mention_count INTEGER DEFAULT 0,
                    context TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                );
                CREATE TABLE IF NOT EXISTS entity_mentions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT,
                    entity_type TEXT,
                    entity_name TEXT,
                    timestamp REAL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_date ON conversations(date);
                CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp);
                CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status);
                CREATE INDEX IF NOT EXISTS idx_actions_timestamp ON actions(timestamp);
                CREATE INDEX IF NOT EXISTS idx_entity_mentions_name ON entity_mentions(entity_name);
                CREATE INDEX IF NOT EXISTS idx_speakers_name ON speakers(name);

                -- CIL: Utterances (atomic unit)
                CREATE TABLE IF NOT EXISTS utterances (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    speaker_id TEXT REFERENCES speakers(id),
                    text TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL NOT NULL,
                    confidence REAL,
                    is_command INTEGER DEFAULT 0,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                );
                CREATE INDEX IF NOT EXISTS idx_utterances_conversation ON utterances(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_utterances_speaker ON utterances(speaker_id);

                -- CIL: Relationships (entity graph)
                CREATE TABLE IF NOT EXISTS relationships (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    evidence TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_rel_source ON relationships(source_id);
                CREATE INDEX IF NOT EXISTS idx_rel_target ON relationships(target_id);
                CREATE INDEX IF NOT EXISTS idx_rel_type ON relationships(relation_type);
            """)

            # TTL column on conversations (idempotent)
            try:
                c.execute("ALTER TABLE conversations ADD COLUMN ttl_expires TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists

            # FTS5 for utterances
            c.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS utterances_fts USING fts5(
                    text, content=utterances, content_rowid=rowid,
                    tokenize='porter unicode61'
                )
            """)

            # FTS sync triggers
            c.executescript("""
                CREATE TRIGGER IF NOT EXISTS utterances_ai AFTER INSERT ON utterances BEGIN
                    INSERT INTO utterances_fts(rowid, text) VALUES (new.rowid, new.text);
                END;
                CREATE TRIGGER IF NOT EXISTS utterances_ad AFTER DELETE ON utterances BEGIN
                    INSERT INTO utterances_fts(utterances_fts, rowid, text) VALUES('delete', old.rowid, old.text);
                END;
                CREATE TRIGGER IF NOT EXISTS utterances_au AFTER UPDATE ON utterances BEGIN
                    INSERT INTO utterances_fts(utterances_fts, rowid, text) VALUES('delete', old.rowid, old.text);
                    INSERT INTO utterances_fts(rowid, text) VALUES (new.rowid, new.text);
                END;
            """)

            # Settings table
            c.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)

            c.commit()

        self._init_default_settings()

    # --- Settings ---

    SETTING_DEFAULTS = {
        'wake_words': '["hey jarvis"]',
        'silence_timeout': '3',
        'conversation_end_timeout': '60',
        'transcriber': 'omi',
        'intent_llm_enabled': 'true',
        'intent_llm_model': 'default',
        'ttl_utterances_days': '30',
        'ttl_summaries_days': '90',
        'ttl_relationships_days': '180',
        'webhook_port': '8900',
        'dashboard_port': '8960',
    }

    def _init_default_settings(self):
        with self._lock:
            for key, value in self.SETTING_DEFAULTS.items():
                self._conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, value))
            self._conn.commit()

    def get_setting(self, key: str, default=None) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row:
            return row["value"]
        return default

    def set_setting(self, key: str, value: str):
        with self._lock:
            self._conn.execute("""
                INSERT INTO settings (key, value, updated_at) VALUES (?, ?, strftime('%s', 'now'))
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """, (key, value))
            self._conn.commit()

    def get_all_settings(self) -> dict:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def delete_setting(self, key: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            self._conn.commit()
            return cur.rowcount > 0

    # --- Conversations ---

    def save_conversation(self, id: str, timestamp: float, date: str,
                          duration_seconds: float = None, segment_count: int = None,
                          word_count: int = None, speakers: list = None,
                          topics: list = None, transcript: str = None,
                          summary: str = None, file_path: str = None,
                          summary_file_path: str = None):
        with self._lock:
            self._conn.execute("""
                INSERT INTO conversations (id, timestamp, date, duration_seconds, segment_count,
                    word_count, speakers, topics, transcript, summary, file_path, summary_file_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    duration_seconds=excluded.duration_seconds,
                    segment_count=excluded.segment_count,
                    word_count=excluded.word_count,
                    speakers=excluded.speakers,
                    topics=excluded.topics,
                    transcript=excluded.transcript,
                    summary=COALESCE(excluded.summary, conversations.summary),
                    file_path=COALESCE(excluded.file_path, conversations.file_path),
                    summary_file_path=COALESCE(excluded.summary_file_path, conversations.summary_file_path)
            """, (id, timestamp, date, duration_seconds, segment_count, word_count,
                  json.dumps(speakers) if speakers else None,
                  json.dumps(topics) if topics else None,
                  transcript, summary, file_path, summary_file_path))
            self._conn.commit()

    def get_conversations(self, date: str = None, limit: int = 50, search: str = None) -> list[dict]:
        q = "SELECT * FROM conversations"
        params = []
        clauses = []
        if date:
            clauses.append("date = ?")
            params.append(date)
        if search:
            clauses.append("(transcript LIKE ? OR topics LIKE ? OR summary LIKE ?)")
            s = f"%{search}%"
            params.extend([s, s, s])
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(q, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_conversation(self, id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM conversations WHERE id = ?", (id,)).fetchone()
        return self._row_to_dict(row) if row else None

    # --- Actions ---

    def save_action(self, conversation_id: str = None, intent: str = "",
                    params: dict = None, raw_text: str = None,
                    status: str = "pending") -> str:
        action_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute("""
                INSERT INTO actions (id, timestamp, conversation_id, intent, params, raw_text, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (action_id, time.time(), conversation_id, intent,
                  json.dumps(params) if params else None, raw_text, status))
            self._conn.commit()
        return action_id

    def update_action_status(self, action_id: str, status: str, result: str = None):
        with self._lock:
            self._conn.execute("""
                UPDATE actions SET status = ?, result = ?, executed_at = ? WHERE id = ?
            """, (status, result, time.time() if status != "pending" else None, action_id))
            self._conn.commit()

    def get_actions(self, status: str = None, limit: int = 50) -> list[dict]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM actions WHERE status = ? ORDER BY timestamp DESC LIMIT ?",
                (status, limit)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM actions ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # --- Speakers ---

    def get_speakers(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM speakers ORDER BY total_words DESC").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_speaker(self, speaker_id: str, name: str = None, relationship: str = None,
                       words_delta: int = 0, segments_delta: int = 0):
        now = time.time()
        with self._lock:
            existing = self._conn.execute("SELECT * FROM speakers WHERE id = ?", (speaker_id,)).fetchone()
            if existing:
                sets = ["last_seen = ?"]
                params = [now]
                if name is not None:
                    sets.append("name = ?")
                    params.append(name)
                if relationship is not None:
                    sets.append("relationship = ?")
                    params.append(relationship)
                if words_delta:
                    sets.append("total_words = total_words + ?")
                    params.append(words_delta)
                if segments_delta:
                    sets.append("total_segments = total_segments + ?")
                    params.append(segments_delta)
                params.append(speaker_id)
                self._conn.execute(f"UPDATE speakers SET {', '.join(sets)} WHERE id = ?", params)
            else:
                self._conn.execute("""
                    INSERT INTO speakers (id, name, first_seen, last_seen, total_words, total_segments, relationship)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (speaker_id, name, now, now, words_delta, segments_delta, relationship))
            self._conn.commit()

    def get_speaker_stats(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("""
                SELECT id, name, total_words, total_segments, first_seen, last_seen, relationship
                FROM speakers ORDER BY total_words DESC
            """).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # --- Entity Mentions ---

    def save_entity_mention(self, conversation_id: str, entity_type: str, entity_name: str):
        with self._lock:
            self._conn.execute("""
                INSERT INTO entity_mentions (conversation_id, entity_type, entity_name, timestamp)
                VALUES (?, ?, ?, ?)
            """, (conversation_id, entity_type, entity_name, time.time()))
            self._conn.commit()

    def search_entities(self, query: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("""
                SELECT * FROM entity_mentions WHERE entity_name LIKE ?
                ORDER BY timestamp DESC LIMIT 100
            """, (f"%{query}%",)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # --- Analytics ---

    def get_analytics(self, period: str = "today") -> dict:
        import datetime as dt
        now = dt.datetime.now()
        if period == "today":
            date_filter = now.strftime("%Y-%m-%d")
            where = "date = ?"
            params = [date_filter]
        elif period == "week":
            week_ago = (now - dt.timedelta(days=7)).strftime("%Y-%m-%d")
            where = "date >= ?"
            params = [week_ago]
        elif period == "month":
            month_ago = (now - dt.timedelta(days=30)).strftime("%Y-%m-%d")
            where = "date >= ?"
            params = [month_ago]
        else:
            where = "1=1"
            params = []

        with self._lock:
            row = self._conn.execute(f"""
                SELECT COUNT(*) as count, COALESCE(SUM(word_count),0) as words,
                       COALESCE(SUM(segment_count),0) as segments,
                       COALESCE(SUM(duration_seconds),0) as duration
                FROM conversations WHERE {where}
            """, params).fetchone()

        return {
            "period": period,
            "conversation_count": row["count"],
            "total_words": row["words"],
            "total_segments": row["segments"],
            "total_duration_s": row["duration"],
        }

    # --- Context ---

    def get_recent_context(self, minutes: int = 30) -> list[dict]:
        cutoff = time.time() - (minutes * 60)
        with self._lock:
            rows = self._conn.execute("""
                SELECT id, transcript, speakers, topics, summary
                FROM conversations WHERE timestamp >= ?
                ORDER BY timestamp DESC
            """, (cutoff,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # --- Contacts ---

    def save_contact(self, id: str, name: str, email: str = None, phone: str = None,
                     relationship: str = None):
        with self._lock:
            self._conn.execute("""
                INSERT INTO contacts (id, name, email, phone, relationship)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, email=COALESCE(excluded.email, contacts.email),
                    phone=COALESCE(excluded.phone, contacts.phone),
                    relationship=COALESCE(excluded.relationship, contacts.relationship)
            """, (id, name, email, phone, relationship))
            self._conn.commit()

    def get_contacts(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM contacts ORDER BY name").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete_contact(self, id: str):
        with self._lock:
            self._conn.execute("DELETE FROM contacts WHERE id = ?", (id,))
            self._conn.commit()

    # --- Address Book Contacts ---

    def save_address_book_contact(self, first_name: str, last_name: str = None, 
                                 alias: str = None, category: str = "personal", 
                                 phone: str = None, email: str = None, 
                                 slack: str = None, notes: str = None) -> int:
        """Save a new address book contact and return its ID."""
        with self._lock:
            cursor = self._conn.execute("""
                INSERT INTO address_book_contacts 
                (first_name, last_name, alias, category, phone, email, slack, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (first_name, last_name, alias, category, phone, email, slack, notes))
            contact_id = cursor.lastrowid
            self._conn.commit()
            return contact_id

    def get_address_book_contact(self, contact_id: int) -> dict | None:
        """Get a single address book contact by ID."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM address_book_contacts WHERE id = ?", 
                (contact_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_all_address_book_contacts(self, category: str = None) -> list[dict]:
        """Get all address book contacts, optionally filtered by category."""
        with self._lock:
            if category:
                rows = self._conn.execute(
                    "SELECT * FROM address_book_contacts WHERE category = ? ORDER BY first_name, last_name", 
                    (category,)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM address_book_contacts ORDER BY first_name, last_name"
                ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def search_address_book_contacts(self, query: str) -> list[dict]:
        """Search contacts by name, alias, email, or phone."""
        query_pattern = f"%{query.lower()}%"
        with self._lock:
            rows = self._conn.execute("""
                SELECT * FROM address_book_contacts 
                WHERE lower(first_name) LIKE ? 
                   OR lower(last_name) LIKE ? 
                   OR lower(alias) LIKE ? 
                   OR lower(email) LIKE ? 
                   OR lower(phone) LIKE ?
                ORDER BY first_name, last_name
            """, (query_pattern, query_pattern, query_pattern, query_pattern, query_pattern)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_address_book_contact(self, contact_id: int, **kwargs) -> bool:
        """Update address book contact fields."""
        if not kwargs:
            return False
        
        # Build SET clause dynamically
        valid_fields = {'first_name', 'last_name', 'alias', 'category', 'phone', 'email', 'slack', 'notes'}
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        
        if not updates:
            return False
        
        set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values())
        values.append(contact_id)  # For WHERE clause
        
        with self._lock:
            cursor = self._conn.execute(f"""
                UPDATE address_book_contacts 
                SET {set_clause}, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, values)
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_address_book_contact(self, contact_id: int) -> bool:
        """Delete an address book contact."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM address_book_contacts WHERE id = ?", (contact_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def resolve_address_book_contact(self, name: str) -> dict | None:
        """Fuzzy match contact by first_name, last_name, or alias (case-insensitive).
        
        This is the KEY function for voice command resolution.
        Returns best match or None.
        """
        name_lower = name.lower().strip()
        
        with self._lock:
            # 1. Exact alias match (highest priority)
            row = self._conn.execute("""
                SELECT * FROM address_book_contacts 
                WHERE lower(alias) = ? AND alias IS NOT NULL AND alias != ''
            """, (name_lower,)).fetchone()
            if row:
                return self._row_to_dict(row)
            
            # 2. Exact first name match
            row = self._conn.execute("""
                SELECT * FROM address_book_contacts 
                WHERE lower(first_name) = ?
            """, (name_lower,)).fetchone()
            if row:
                return self._row_to_dict(row)
            
            # 3. Full name match (first + last)
            name_parts = name_lower.split()
            if len(name_parts) >= 2:
                first_part = name_parts[0]
                last_part = ' '.join(name_parts[1:])
                row = self._conn.execute("""
                    SELECT * FROM address_book_contacts 
                    WHERE lower(first_name) = ? AND lower(last_name) = ?
                """, (first_part, last_part)).fetchone()
                if row:
                    return self._row_to_dict(row)
            
            # 4. Partial match with confidence (starts with)
            rows = self._conn.execute("""
                SELECT * FROM address_book_contacts 
                WHERE lower(first_name) LIKE ? OR lower(alias) LIKE ?
                ORDER BY 
                    CASE 
                        WHEN lower(first_name) = ? THEN 1
                        WHEN lower(alias) = ? THEN 2
                        WHEN lower(first_name) LIKE ? THEN 3
                        WHEN lower(alias) LIKE ? THEN 4
                        ELSE 5
                    END
                LIMIT 1
            """, (f"{name_lower}%", f"{name_lower}%", name_lower, name_lower, f"{name_lower}%", f"{name_lower}%")).fetchall()
            
            if rows:
                return self._row_to_dict(rows[0])
        
        return None

    def migrate_contacts_from_json(self, json_file_path: str) -> int:
        """Migrate contacts from existing contacts.json to the new address book table.
        
        Returns the number of contacts migrated.
        """
        import json
        from pathlib import Path
        
        json_path = Path(json_file_path)
        if not json_path.exists():
            logger.warning(f"Contacts JSON file not found: {json_file_path}")
            return 0
        
        try:
            with open(json_path, 'r') as f:
                contacts_data = json.load(f)
            
            migrated_count = 0
            
            for name, info in contacts_data.items():
                # Skip if already migrated (check by name)
                existing = self.resolve_address_book_contact(name)
                if existing:
                    continue
                
                # Extract data from old format
                email = info.get('email')
                phone = info.get('phone')
                aliases = info.get('aliases', [])
                alias = aliases[0] if aliases else None
                
                # Use name as first_name, try to split if it contains spaces
                name_parts = name.strip().split()
                first_name = name_parts[0] if name_parts else name
                last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else None
                
                # Save to new table
                self.save_address_book_contact(
                    first_name=first_name,
                    last_name=last_name,
                    alias=alias,
                    category='personal',  # Default category for migrated contacts
                    phone=phone,
                    email=email,
                    notes=f"Migrated from contacts.json. Original aliases: {', '.join(aliases) if aliases else 'none'}"
                )
                
                migrated_count += 1
                logger.info(f"Migrated contact: {name} -> {first_name} {last_name or ''}")
            
            return migrated_count
            
        except Exception as e:
            logger.error(f"Error migrating contacts from JSON: {e}")
            return 0

    # --- Utterances ---

    def save_utterance(self, id: str, conversation_id: str, speaker_id: str,
                       text: str, started_at: float, ended_at: float,
                       confidence: float = None, is_command: bool = False):
        with self._lock:
            self._conn.execute("""
                INSERT INTO utterances (id, conversation_id, speaker_id, text, started_at, ended_at, confidence, is_command)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text=excluded.text, confidence=excluded.confidence, is_command=excluded.is_command
            """, (id, conversation_id, speaker_id, text, started_at, ended_at, confidence, int(is_command)))
            self._conn.commit()

    def save_utterances_batch(self, utterances_list: list[dict]):
        """Bulk insert utterances. Each dict needs: id, conversation_id, speaker_id, text, started_at, ended_at."""
        with self._lock:
            self._conn.executemany("""
                INSERT OR IGNORE INTO utterances (id, conversation_id, speaker_id, text, started_at, ended_at, confidence, is_command)
                VALUES (:id, :conversation_id, :speaker_id, :text, :started_at, :ended_at, :confidence, :is_command)
            """, [{
                "id": u["id"], "conversation_id": u["conversation_id"],
                "speaker_id": u.get("speaker_id"), "text": u["text"],
                "started_at": u["started_at"], "ended_at": u["ended_at"],
                "confidence": u.get("confidence"), "is_command": int(u.get("is_command", False)),
            } for u in utterances_list])
            self._conn.commit()

    def search_utterances(self, query: str, limit: int = 20) -> list[dict]:
        """FTS5 search across utterances."""
        with self._lock:
            rows = self._conn.execute("""
                SELECT u.*, highlight(utterances_fts, 0, '<b>', '</b>') as highlighted
                FROM utterances_fts fts
                JOIN utterances u ON u.rowid = fts.rowid
                WHERE utterances_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query, limit)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_utterances(self, conversation_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM utterances WHERE conversation_id = ? ORDER BY started_at",
                (conversation_id,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # --- Relationships ---

    def save_relationship(self, source_id: str, target_id: str, relation_type: str,
                          evidence: str = None) -> str:
        now = time.time()
        # Check for existing relationship
        with self._lock:
            existing = self._conn.execute("""
                SELECT id, evidence, weight FROM relationships
                WHERE source_id = ? AND target_id = ? AND relation_type = ?
            """, (source_id, target_id, relation_type)).fetchone()

            if existing:
                # Update existing: bump weight, update last_seen, append evidence
                old_evidence = json.loads(existing["evidence"]) if existing["evidence"] else []
                if evidence:
                    old_evidence.append(evidence)
                self._conn.execute("""
                    UPDATE relationships SET weight = weight + 1.0, last_seen = ?, evidence = ?
                    WHERE id = ?
                """, (now, json.dumps(old_evidence[-10:]), existing["id"]))
                self._conn.commit()
                return existing["id"]
            else:
                rel_id = str(uuid.uuid4())
                ev_json = json.dumps([evidence]) if evidence else None
                try:
                    self._conn.execute("""
                        INSERT INTO relationships (id, source_id, target_id, relation_type, weight, first_seen, last_seen, evidence)
                        VALUES (?, ?, ?, ?, 1.0, ?, ?, ?)
                    """, (rel_id, source_id, target_id, relation_type, now, now, ev_json))
                    self._conn.commit()
                    return rel_id
                except IntegrityError as e:
                    logger.warning(f"IntegrityError inserting relationship {source_id} -> {target_id}: {e}")
                    self._conn.rollback()
                    return None

    def get_relationships(self, entity_id: str = None, relation_type: str = None) -> list[dict]:
        q = "SELECT * FROM relationships"
        params = []
        clauses = []
        if entity_id:
            clauses.append("(source_id = ? OR target_id = ?)")
            params.extend([entity_id, entity_id])
        if relation_type:
            clauses.append("relation_type = ?")
            params.append(relation_type)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY weight DESC"
        with self._lock:
            rows = self._conn.execute(q, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_relationship_weight(self, rel_id: str, weight_delta: float):
        with self._lock:
            self._conn.execute(
                "UPDATE relationships SET weight = MAX(0, weight + ?) WHERE id = ?",
                (weight_delta, rel_id))
            self._conn.commit()

    def decay_relationships(self, days_stale: int = 7, decay_rate: float = 0.1):
        """Linear decay for relationships not seen in days_stale days."""
        cutoff = time.time() - (days_stale * 86400)
        with self._lock:
            self._conn.execute("""
                UPDATE relationships SET weight = MAX(0, weight - ?)
                WHERE last_seen < ?
            """, (decay_rate, cutoff))
            # Remove zero-weight relationships
            self._conn.execute("DELETE FROM relationships WHERE weight <= 0")
            self._conn.commit()

    # --- TTL & Audit ---

    def purge_expired(self) -> int:
        """Delete conversations past their TTL. Returns count deleted."""
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        with self._lock:
            cur = self._conn.execute(
                "SELECT id FROM conversations WHERE ttl_expires IS NOT NULL AND ttl_expires < ?",
                (now_iso,))
            ids = [r["id"] for r in cur.fetchall()]
            for cid in ids:
                self._purge_conversation_inner(cid)
            self._conn.commit()
        return len(ids)

    def purge_older_than(self, days: int) -> int:
        cutoff = time.time() - (days * 86400)
        with self._lock:
            cur = self._conn.execute(
                "SELECT id FROM conversations WHERE timestamp < ?", (cutoff,))
            ids = [r["id"] for r in cur.fetchall()]
            for cid in ids:
                self._purge_conversation_inner(cid)
            self._conn.commit()
        return len(ids)

    def purge_conversation(self, conversation_id: str):
        with self._lock:
            self._purge_conversation_inner(conversation_id)
            self._conn.commit()

    def _purge_conversation_inner(self, conversation_id: str):
        """Delete a conversation and all related data. Must be called within lock."""
        self._conn.execute("DELETE FROM utterances WHERE conversation_id = ?", (conversation_id,))
        self._conn.execute("DELETE FROM entity_mentions WHERE conversation_id = ?", (conversation_id,))
        self._conn.execute("DELETE FROM actions WHERE conversation_id = ?", (conversation_id,))
        self._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    def audit(self) -> dict:
        """Return counts of all data types and storage size."""
        with self._lock:
            counts = {}
            for table in ("conversations", "utterances", "speakers", "contacts",
                          "actions", "projects", "entity_mentions", "relationships"):
                try:
                    row = self._conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
                    counts[table] = row["c"]
                except Exception:
                    counts[table] = 0
        # Storage size
        try:
            db_size = os.path.getsize(self._db_path)
        except Exception:
            db_size = 0
        counts["storage_bytes"] = db_size
        return counts

    # --- Helpers ---

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        # Parse JSON fields
        for k in ("speakers", "topics", "params", "keywords"):
            if k in d and isinstance(d[k], str):
                try:
                    d[k] = json.loads(d[k])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

    def close(self):
        self._conn.close()
