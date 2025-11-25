"""
Database management for !Clipit
Handles SQLite database operations for tokens and clip statistics
"""
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any
from logs import get_logger; log = get_logger(__name__)


class Database:
    def __init__(self, db_path: str = "clipitbot.db"):
        self.db_path = db_path
        self.init_database()

    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Auth tokens table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Clip statistics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clip_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clip_id TEXT NOT NULL UNIQUE,
                clip_url TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                voters TEXT,
                comments TEXT,
                created_by TEXT,
                time_to_generate REAL,
                time_into_broadcast TEXT,
                broadcaster_name TEXT,
                clip_title TEXT,
                directory TEXT,
                thumbnail_url TEXT
            )
        """)

        conn.commit()
        conn.close()
        log.info("Database initialized successfully")

    def save_tokens(self, access_token: str, refresh_token: str, expires_at: int):
        """Save or update authentication tokens"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Check if tokens exist
        cursor.execute("SELECT id FROM auth_tokens LIMIT 1")
        existing = cursor.fetchone()

        if existing:
            # Update existing tokens
            cursor.execute("""
                UPDATE auth_tokens 
                SET access_token = ?, refresh_token = ?, expires_at = ?, updated_at = ?
                WHERE id = ?
            """, (access_token, refresh_token, expires_at, datetime.now(), existing['id']))
        else:
            # Insert new tokens
            cursor.execute("""
                INSERT INTO auth_tokens (access_token, refresh_token, expires_at)
                VALUES (?, ?, ?)
            """, (access_token, refresh_token, expires_at))

        conn.commit()
        conn.close()
        log.info("Authentication tokens saved")

    def get_tokens(self) -> Optional[Dict[str, Any]]:
        """Retrieve authentication tokens"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM auth_tokens LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'access_token': row['access_token'],
                'refresh_token': row['refresh_token'],
                'expires_at': row['expires_at']
            }
        return None

    def clear_tokens(self):
        """Clear all authentication tokens from database"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM auth_tokens")
        conn.commit()
        conn.close()
        log.info("Authentication tokens cleared")

    def save_clip_statistics(self, clip_id: str, clip_url: str, voters: list, comments: str, created_by: str, 
                            time_to_generate: float = None, time_into_broadcast: str = None,
                            broadcaster_name: str = None, clip_title: str = None,
                            directory: str = None, thumbnail_url: str = None):
        """Save clip statistics to database"""
        conn = self.get_connection()
        cursor = conn.cursor()

        voters_str = ",".join(voters) if voters else ""

        try:
            cursor.execute("""
                INSERT INTO clip_statistics (clip_id, clip_url, voters, comments, created_by, 
                                           time_to_generate, time_into_broadcast, broadcaster_name,
                                           clip_title, directory, thumbnail_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (clip_id, clip_url, voters_str, comments, created_by, time_to_generate, 
                  time_into_broadcast, broadcaster_name, clip_title, directory, thumbnail_url))
            conn.commit()
            log.info(f"Clip statistics saved: {clip_id}")
        except sqlite3.IntegrityError:
            log.warning(f"Clip {clip_id} already exists in database")
        finally:
            conn.close()

    def get_total_clips_generated(self) -> int:
        """Get total number of clips generated"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM clip_statistics")
        result = cursor.fetchone()
        conn.close()

        return result[0] if result else 0
