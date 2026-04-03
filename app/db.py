"""
Database management for !Clipit
"""

import hashlib
from datetime import UTC, datetime

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, func, select

from app.core.logs import get_logger
from app.core.security import SecretBox
from app.models import (
    AppSession,
    BroadcasterInstallation,
    BroadcasterSettings,
    BroadcasterSettingsUpdate,
    ClipStatistic,
)

log = get_logger(__name__)


class Database:
    def __init__(
        self,
        database_url: str = "sqlite:///clipitbot.db",
        *,
        secret_box: SecretBox,
    ):
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args)
        self.secret_box = secret_box
        self._verify_schema()
        log.info("Database engine initialized successfully")

    def _verify_schema(self):
        inspector = inspect(self.engine)
        tables = {
            "broadcaster_installations": {
                "broadcaster_id",
                "login",
                "display_name",
                "access_token",
                "refresh_token",
                "expires_at",
                "enabled",
            },
            "broadcaster_settings": {
                "broadcaster_id",
                "commands",
                "minimum_votes",
                "command_window",
                "command_cooldown",
                "vote_permissions",
                "subscriber_months",
                "override_permissions",
                "discord_webhook_url",
                "donotallowlist_enabled",
                "donotallowlist_usernames",
            },
            "clip_statistics": {
                "id",
                "clip_id",
                "clip_url",
                "timestamp",
            },
            "app_sessions": {
                "session_id_hash",
                "broadcaster_id",
                "login",
                "csrf_token",
                "expires_at",
            },
        }

        missing_tables = [table_name for table_name in tables if not inspector.has_table(table_name)]
        if missing_tables:
            joined = ", ".join(missing_tables)
            raise RuntimeError(
                f"Database schema is missing required tables: {joined}. "
                "Run `uv run alembic upgrade head` before starting the app."
            )

        missing_columns: list[str] = []
        for table_name, required_columns in tables.items():
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name in sorted(required_columns - columns):
                missing_columns.append(f"{table_name}.{column_name}")

        if missing_columns:
            joined = ", ".join(missing_columns)
            raise RuntimeError(
                f"Database schema is out of date. Missing columns: {joined}. "
                "Run `uv run alembic upgrade head` before starting the app."
            )

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def save_broadcaster(
        self,
        broadcaster_id: str,
        login: str,
        display_name: str,
        access_token: str,
        refresh_token: str,
        expires_at: int,
        enabled: bool = True,
    ) -> BroadcasterInstallation:
        with Session(self.engine) as session:
            broadcaster = session.get(BroadcasterInstallation, broadcaster_id)
            if broadcaster is None:
                broadcaster = BroadcasterInstallation(
                    broadcaster_id=broadcaster_id,
                    login=login.lower(),
                    display_name=display_name,
                    access_token=self.secret_box.encrypt(access_token),
                    refresh_token=self.secret_box.encrypt(refresh_token),
                    expires_at=expires_at,
                    enabled=enabled,
                )
                session.add(broadcaster)
            else:
                broadcaster.login = login.lower()
                broadcaster.display_name = display_name
                broadcaster.access_token = self.secret_box.encrypt(access_token)
                broadcaster.refresh_token = self.secret_box.encrypt(refresh_token)
                broadcaster.expires_at = expires_at
                broadcaster.enabled = enabled
                broadcaster.updated_at = self._now()

            session.commit()
            session.refresh(broadcaster)
            return self._decrypt_broadcaster(broadcaster)

    def save_broadcaster_settings(
        self,
        broadcaster_id: str,
        settings: BroadcasterSettingsUpdate,
    ) -> BroadcasterSettings:
        encrypted_payload = self._encrypt_settings_payload(settings.model_dump())
        with Session(self.engine) as session:
            broadcaster_settings = session.get(BroadcasterSettings, broadcaster_id)
            if broadcaster_settings is None:
                broadcaster_settings = BroadcasterSettings.model_validate(
                    {
                        "broadcaster_id": broadcaster_id,
                        **encrypted_payload,
                    }
                )
                session.add(broadcaster_settings)
            else:
                for field_name, value in encrypted_payload.items():
                    setattr(broadcaster_settings, field_name, value)
                broadcaster_settings.updated_at = self._now()

            session.commit()
            session.refresh(broadcaster_settings)
            return self._decrypt_settings(broadcaster_settings)

    def ensure_broadcaster_settings(
        self,
        broadcaster_id: str,
        defaults: BroadcasterSettingsUpdate,
    ) -> BroadcasterSettings:
        existing = self.get_broadcaster_settings(broadcaster_id)
        if existing is not None:
            return existing
        return self.save_broadcaster_settings(broadcaster_id, defaults)

    def get_broadcaster_settings(self, broadcaster_id: str) -> BroadcasterSettings | None:
        with Session(self.engine) as session:
            settings = session.get(BroadcasterSettings, broadcaster_id)
            if settings is None:
                return None
            if not self.secret_box.is_encrypted(settings.discord_webhook_url):
                settings.discord_webhook_url = self.secret_box.encrypt(settings.discord_webhook_url)
                settings.updated_at = self._now()
                session.add(settings)
                session.commit()
                session.refresh(settings)
            return self._decrypt_settings(settings)

    def get_broadcaster(self, broadcaster_id: str) -> BroadcasterInstallation | None:
        with Session(self.engine) as session:
            broadcaster = session.get(BroadcasterInstallation, broadcaster_id)
            if broadcaster is None:
                return None
            self._normalize_broadcaster_secrets(session, broadcaster)
            return self._decrypt_broadcaster(broadcaster)

    def get_all_broadcasters(self) -> list[BroadcasterInstallation]:
        with Session(self.engine) as session:
            statement = select(BroadcasterInstallation).order_by(BroadcasterInstallation.login)
            broadcasters = list(session.exec(statement).all())
            for broadcaster in broadcasters:
                self._normalize_broadcaster_secrets(session, broadcaster)
            return [self._decrypt_broadcaster(broadcaster) for broadcaster in broadcasters]

    def get_enabled_broadcasters(self) -> list[BroadcasterInstallation]:
        with Session(self.engine) as session:
            statement = (
                select(BroadcasterInstallation)
                .where(BroadcasterInstallation.enabled)
                .order_by(BroadcasterInstallation.login)
            )
            broadcasters = list(session.exec(statement).all())
            for broadcaster in broadcasters:
                self._normalize_broadcaster_secrets(session, broadcaster)
            return [self._decrypt_broadcaster(broadcaster) for broadcaster in broadcasters]

    def set_broadcaster_enabled(self, broadcaster_id: str, enabled: bool):
        with Session(self.engine) as session:
            broadcaster = session.get(BroadcasterInstallation, broadcaster_id)
            if broadcaster is None:
                return
            broadcaster.enabled = enabled
            broadcaster.updated_at = self._now()
            session.add(broadcaster)
            session.commit()
            log.warning("Broadcaster %s: enabled=%s", broadcaster_id, enabled)

    def delete_broadcaster(self, broadcaster_id: str):
        with Session(self.engine) as session:
            settings = session.get(BroadcasterSettings, broadcaster_id)
            broadcaster = session.get(BroadcasterInstallation, broadcaster_id)
            sessions = list(
                session.exec(
                    select(AppSession).where(AppSession.broadcaster_id == broadcaster_id)
                ).all()
            )
            if settings is not None:
                session.delete(settings)
            if broadcaster is not None:
                session.delete(broadcaster)
            for app_session in sessions:
                session.delete(app_session)
            session.commit()
            log.warning("Broadcaster disconnected and removed: %s", broadcaster_id)

    def save_session(
        self,
        *,
        session_token: str,
        broadcaster_id: str,
        login: str,
        csrf_token: str,
        expires_at: int,
    ) -> AppSession:
        session_id_hash = self._hash_session_token(session_token)
        with Session(self.engine) as session:
            app_session = AppSession(
                session_id_hash=session_id_hash,
                broadcaster_id=broadcaster_id,
                login=login,
                csrf_token=csrf_token,
                expires_at=expires_at,
            )
            session.merge(app_session)
            session.commit()
            return app_session

    def get_session(self, session_token: str) -> AppSession | None:
        with Session(self.engine) as session:
            return session.get(AppSession, self._hash_session_token(session_token))

    def delete_session(self, session_token: str):
        with Session(self.engine) as session:
            app_session = session.get(AppSession, self._hash_session_token(session_token))
            if app_session is not None:
                session.delete(app_session)
                session.commit()

    def delete_sessions_for_broadcaster(self, broadcaster_id: str):
        with Session(self.engine) as session:
            app_sessions = list(
                session.exec(
                    select(AppSession).where(AppSession.broadcaster_id == broadcaster_id)
                ).all()
            )
            for app_session in app_sessions:
                session.delete(app_session)
            if app_sessions:
                session.commit()

    def get_connected_broadcaster_count(self) -> int:
        with Session(self.engine) as session:
            statement = (
                select(func.count())
                .select_from(BroadcasterInstallation)
                .where(BroadcasterInstallation.enabled)
            )
            result = session.exec(statement).one()
            return int(result or 0)

    def save_clip_statistics(
        self,
        clip_id: str,
        clip_url: str,
        voters: list[str],
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
        with Session(self.engine) as session:
            statistic = ClipStatistic(
                clip_id=clip_id,
                clip_url=clip_url,
                voters=",".join(voters) if voters else "",
                comments=comments,
                created_by=created_by,
                time_to_generate=time_to_generate,
                time_into_broadcast=time_into_broadcast,
                broadcaster_id=broadcaster_id,
                broadcaster_name=broadcaster_name,
                clip_title=clip_title,
                directory=directory,
                thumbnail_url=thumbnail_url,
            )
            session.add(statistic)
            try:
                session.commit()
                log.info("Clip statistics saved: %s", clip_id)
            except IntegrityError:
                session.rollback()
                log.warning("Clip %s already exists in database", clip_id)

    def _hash_session_token(self, session_token: str) -> str:
        return hashlib.sha256(session_token.encode("utf-8")).hexdigest()

    def _normalize_broadcaster_secrets(
        self,
        session: Session,
        broadcaster: BroadcasterInstallation,
    ):
        updated = False
        if not self.secret_box.is_encrypted(broadcaster.access_token):
            broadcaster.access_token = self.secret_box.encrypt(broadcaster.access_token)
            updated = True
        if not self.secret_box.is_encrypted(broadcaster.refresh_token):
            broadcaster.refresh_token = self.secret_box.encrypt(broadcaster.refresh_token)
            updated = True
        if updated:
            broadcaster.updated_at = self._now()
            session.add(broadcaster)
            session.commit()
            session.refresh(broadcaster)

    def _decrypt_broadcaster(
        self,
        broadcaster: BroadcasterInstallation,
    ) -> BroadcasterInstallation:
        return BroadcasterInstallation.model_validate(
            {
                **broadcaster.model_dump(),
                "access_token": self.secret_box.decrypt(broadcaster.access_token),
                "refresh_token": self.secret_box.decrypt(broadcaster.refresh_token),
            }
        )

    def _encrypt_settings_payload(self, payload: dict[str, object]) -> dict[str, object]:
        data = dict(payload)
        data["discord_webhook_url"] = self.secret_box.encrypt(
            str(data.get("discord_webhook_url", "") or "")
        )
        return data

    def _decrypt_settings(self, settings: BroadcasterSettings) -> BroadcasterSettings:
        return BroadcasterSettings.model_validate(
            {
                **settings.model_dump(),
                "discord_webhook_url": self.secret_box.decrypt(settings.discord_webhook_url),
            }
        )
