from datetime import datetime, UTC
from sqlmodel import Field, SQLModel

from .broadcaster_settings import BroadcasterSettingsSnapshot


class BroadcasterInstallation(SQLModel, table=True):
    __tablename__ = "broadcaster_installations"

    broadcaster_id: str = Field(primary_key=True)
    login: str = Field(index=True, unique=True)
    display_name: str
    access_token: str
    refresh_token: str
    expires_at: int
    enabled: bool = True
    worker_error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class WorkerStatus(SQLModel):
    worker_present: bool
    worker_running: bool
    worker_error: str | None = None


class BroadcasterSnapshot(SQLModel):
    broadcaster_id: str
    login: str
    display_name: str
    enabled: bool
    expires_at: int
    worker: WorkerStatus
    settings: BroadcasterSettingsSnapshot | None = None
