from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class AppSession(SQLModel, table=True):
    __tablename__ = "app_sessions"

    session_id_hash: str = Field(primary_key=True)
    broadcaster_id: str = Field(
        foreign_key="broadcaster_installations.broadcaster_id",
        index=True,
    )
    login: str
    csrf_token: str
    expires_at: int
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
