"""
Database management for !Clipit
Handles SQLite database operations for broadcaster auth, settings, and clip statistics
"""

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional, cast

from config import BroadcasterConfig
from logs import get_logger

log = get_logger(__name__)


class Database:
    def __init__(self, db_path: str = "clipitbot.db"):
        self.db_path = db_path
        self.init_database()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS broadcaster_installations (
                broadcaster_id TEXT PRIMARY KEY,
                login TEXT NOT NULL UNIQUE,
                display_name TEXT,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS broadcaster_settings (
                broadcaster_id TEXT PRIMARY KEY,
                commands_json TEXT NOT NULL,
                minimum_votes INTEGER NOT NULL,
                command_window INTEGER NOT NULL,
                command_cooldown INTEGER NOT NULL,
                vote_permissions TEXT NOT NULL,
                subscriber_months TEXT NOT NULL,
                override_permissions TEXT NOT NULL,
                discord_webhook_url TEXT NOT NULL DEFAULT '',
                donotallowlist_enabled INTEGER NOT NULL DEFAULT 0,
                donotallowlist_usernames_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (broadcaster_id) REFERENCES broadcaster_installations(broadcaster_id)
            )
            """
        )

        cursor.execute(
            """
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
                broadcaster_id TEXT,
                broadcaster_name TEXT,
                clip_title TEXT,
                directory TEXT,
                thumbnail_url TEXT
            )
            """
        )

        self._ensure_column(cursor, "clip_statistics", "broadcaster_id", "TEXT")
        self._ensure_column(cursor, "clip_statistics", "broadcaster_name", "TEXT")
        self._ensure_column(cursor, "clip_statistics", "thumbnail_url", "TEXT")

        conn.commit()
        conn.close()
        log.info("Database initialized successfully")

    def _ensure_column(
        self, cursor: sqlite3.Cursor, table_name: str, column_name: str, column_type: str
    ):
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = {row[1] for row in cursor.fetchall()}
        if column_name not in columns:
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )

    def _row_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        return dict(row) if row else None

    def _encode_json(self, value: Any) -> str:
        return json.dumps(value, separators=(",", ":"))

    def _decode_json_list(self, value: str | None) -> list[str]:
        if not value:
            return []
        decoded = json.loads(value)
        return [str(item) for item in decoded] if isinstance(decoded, list) else []

    def _settings_row_to_dict(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        data = dict(row)
        commands_json = cast(str | None, data.pop("commands_json", None))
        deny_list_json = cast(str | None, data.pop("donotallowlist_usernames_json", None))
        data["commands"] = self._decode_json_list(commands_json)
        data["donotallowlist_enabled"] = bool(data["donotallowlist_enabled"])
        data["donotallowlist_usernames"] = self._decode_json_list(deny_list_json)
        return data

    def save_tokens(self, access_token: str, refresh_token: str, expires_at: int):
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM auth_tokens LIMIT 1")
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE auth_tokens
                SET access_token = ?, refresh_token = ?, expires_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    access_token,
                    refresh_token,
                    expires_at,
                    datetime.now(),
                    existing["id"],
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO auth_tokens (access_token, refresh_token, expires_at)
                VALUES (?, ?, ?)
                """,
                (access_token, refresh_token, expires_at),
            )

        conn.commit()
        conn.close()
        log.info("Legacy authentication tokens saved")

    def get_tokens(self) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM auth_tokens LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "access_token": row["access_token"],
                "refresh_token": row["refresh_token"],
                "expires_at": row["expires_at"],
            }
        return None

    def clear_tokens(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM auth_tokens")
        conn.commit()
        conn.close()
        log.info("Legacy authentication tokens cleared")

    def save_broadcaster(
        self,
        broadcaster_id: str,
        login: str,
        display_name: str,
        access_token: str,
        refresh_token: str,
        expires_at: int,
        enabled: bool = True,
    ):
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO broadcaster_installations (
                broadcaster_id,
                login,
                display_name,
                access_token,
                refresh_token,
                expires_at,
                enabled,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(broadcaster_id) DO UPDATE SET
                login = excluded.login,
                display_name = excluded.display_name,
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at,
                enabled = excluded.enabled,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                broadcaster_id,
                login.lower(),
                display_name,
                access_token,
                refresh_token,
                expires_at,
                1 if enabled else 0,
            ),
        )

        conn.commit()
        conn.close()
        log.info("Broadcaster installation saved: %s", login.lower())

    def save_broadcaster_settings(
        self,
        broadcaster_id: str,
        settings: BroadcasterConfig,
    ):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO broadcaster_settings (
                broadcaster_id,
                commands_json,
                minimum_votes,
                command_window,
                command_cooldown,
                vote_permissions,
                subscriber_months,
                override_permissions,
                discord_webhook_url,
                donotallowlist_enabled,
                donotallowlist_usernames_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(broadcaster_id) DO UPDATE SET
                commands_json = excluded.commands_json,
                minimum_votes = excluded.minimum_votes,
                command_window = excluded.command_window,
                command_cooldown = excluded.command_cooldown,
                vote_permissions = excluded.vote_permissions,
                subscriber_months = excluded.subscriber_months,
                override_permissions = excluded.override_permissions,
                discord_webhook_url = excluded.discord_webhook_url,
                donotallowlist_enabled = excluded.donotallowlist_enabled,
                donotallowlist_usernames_json = excluded.donotallowlist_usernames_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                broadcaster_id,
                self._encode_json(settings.commands),
                settings.minimum_votes,
                settings.command_window,
                settings.command_cooldown,
                settings.vote_permissions,
                settings.subscriber_months,
                settings.override_permissions,
                settings.discord_webhook_url,
                1 if settings.donotallowlist_enabled else 0,
                self._encode_json(settings.donotallowlist_usernames),
            ),
        )
        conn.commit()
        conn.close()

    def ensure_broadcaster_settings(
        self,
        broadcaster_id: str,
        defaults: BroadcasterConfig,
    ) -> Dict[str, Any]:
        existing = self.get_broadcaster_settings(broadcaster_id)
        if existing:
            return existing
        self.save_broadcaster_settings(broadcaster_id, defaults)
        return self.get_broadcaster_settings(broadcaster_id) or defaults.to_dict()

    def get_broadcaster_settings(self, broadcaster_id: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM broadcaster_settings WHERE broadcaster_id = ?",
            (broadcaster_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return self._settings_row_to_dict(row)

    def get_broadcaster(self, broadcaster_id: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM broadcaster_installations WHERE broadcaster_id = ?",
            (broadcaster_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def get_broadcaster_by_login(self, login: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM broadcaster_installations WHERE login = ?",
            (login.lower(),),
        )
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)

    def get_all_broadcasters(self) -> list[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM broadcaster_installations ORDER BY login ASC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_enabled_broadcasters(self) -> list[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM broadcaster_installations WHERE enabled = 1 ORDER BY login ASC"
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def set_broadcaster_enabled(self, broadcaster_id: str, enabled: bool):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE broadcaster_installations
            SET enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE broadcaster_id = ?
            """,
            (1 if enabled else 0, broadcaster_id),
        )
        conn.commit()
        conn.close()
        log.warning("Broadcaster %s: enabled=%s", broadcaster_id, enabled)

    def disable_broadcaster(self, broadcaster_id: str):
        self.set_broadcaster_enabled(broadcaster_id, False)

    def delete_broadcaster(self, broadcaster_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM broadcaster_settings WHERE broadcaster_id = ?",
            (broadcaster_id,),
        )
        cursor.execute(
            "DELETE FROM broadcaster_installations WHERE broadcaster_id = ?",
            (broadcaster_id,),
        )
        conn.commit()
        conn.close()
        log.warning("Broadcaster disconnected and removed: %s", broadcaster_id)

    def get_connected_broadcaster_count(self) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM broadcaster_installations WHERE enabled = 1"
        )
        result = cursor.fetchone()
        conn.close()
        return int(result[0]) if result else 0

    def save_clip_statistics(
        self,
        clip_id: str,
        clip_url: str,
        voters: list,
        comments: str,
        created_by: str,
        time_to_generate: float | None = None,
        time_into_broadcast: str | None = None,
        broadcaster_id: str | None = None,
        broadcaster_name: str | None = None,
        clip_title: str | None = None,
        directory: str | None = None,
        thumbnail_url: str | None = None,
    ):
        conn = self.get_connection()
        cursor = conn.cursor()

        voters_str = ",".join(voters) if voters else ""

        try:
            cursor.execute(
                """
                INSERT INTO clip_statistics (
                    clip_id,
                    clip_url,
                    voters,
                    comments,
                    created_by,
                    time_to_generate,
                    time_into_broadcast,
                    broadcaster_id,
                    broadcaster_name,
                    clip_title,
                    directory,
                    thumbnail_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clip_id,
                    clip_url,
                    voters_str,
                    comments,
                    created_by,
                    time_to_generate,
                    time_into_broadcast,
                    broadcaster_id,
                    broadcaster_name,
                    clip_title,
                    directory,
                    thumbnail_url,
                ),
            )
            conn.commit()
            log.info("Clip statistics saved: %s", clip_id)
        except sqlite3.IntegrityError:
            log.warning("Clip %s already exists in database", clip_id)
        finally:
            conn.close()

    def get_total_clips_generated(self, broadcaster_id: str | None = None) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()

        if broadcaster_id:
            cursor.execute(
                "SELECT COUNT(*) FROM clip_statistics WHERE broadcaster_id = ?",
                (broadcaster_id,),
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM clip_statistics")

        result = cursor.fetchone()
        conn.close()
        return int(result[0]) if result else 0
