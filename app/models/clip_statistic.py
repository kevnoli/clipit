from datetime import datetime, UTC
from sqlmodel import Field, SQLModel


class ClipStatistic(SQLModel, table=True):
    __tablename__ = "clip_statistics"

    id: int | None = Field(default=None, primary_key=True)
    clip_id: str = Field(index=True, unique=True)
    clip_url: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    voters: str = ""
    comments: str = ""
    created_by: str = ""
    time_to_generate: float | None = None
    time_into_broadcast: str | None = None
    broadcaster_id: str | None = None
    broadcaster_name: str | None = None
    clip_title: str | None = None
    directory: str | None = None
    thumbnail_url: str | None = None
