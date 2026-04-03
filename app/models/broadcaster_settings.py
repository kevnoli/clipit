from datetime import datetime, UTC
from sqlmodel import Field, SQLModel
from sqlalchemy import JSON, Column


class BroadcasterSettingsUpdate(SQLModel):
    commands: list[str] = Field(
        default_factory=lambda: ["!clipit"],
        sa_column=Column(JSON, nullable=False),
    )
    minimum_votes: int = 2
    command_window: int = 15
    command_cooldown: int = 30
    vote_permissions: str = "Everyone"
    subscriber_months: str = "SUB:3"
    override_permissions: str = "Owner"
    discord_webhook_url: str = ""
    donotallowlist_enabled: bool = False
    donotallowlist_usernames: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )


class BroadcasterSettingsPayload(SQLModel):
    commands: list[str] = Field(default_factory=lambda: ["!clipit"])
    minimum_votes: int = 2
    command_window: int = 15
    command_cooldown: int = 30
    vote_permissions: str = "Everyone"
    subscriber_months: str = "SUB:3"
    override_permissions: str = "Owner"
    discord_webhook_url: str | None = None
    clear_discord_webhook: bool = False
    donotallowlist_enabled: bool = False
    donotallowlist_usernames: list[str] = Field(default_factory=list)

    def to_settings_update(
        self,
        existing: "BroadcasterSettingsUpdate | BroadcasterSettings | None" = None,
    ) -> "BroadcasterSettingsUpdate":
        webhook_url = self.discord_webhook_url
        if self.clear_discord_webhook:
            webhook_value = ""
        elif webhook_url is None:
            webhook_value = existing.discord_webhook_url if existing is not None else ""
        else:
            webhook_value = webhook_url

        return BroadcasterSettingsUpdate(
            commands=self.commands,
            minimum_votes=self.minimum_votes,
            command_window=self.command_window,
            command_cooldown=self.command_cooldown,
            vote_permissions=self.vote_permissions,
            subscriber_months=self.subscriber_months,
            override_permissions=self.override_permissions,
            discord_webhook_url=webhook_value,
            donotallowlist_enabled=self.donotallowlist_enabled,
            donotallowlist_usernames=self.donotallowlist_usernames,
        )


class BroadcasterSettingsSnapshot(SQLModel):
    commands: list[str] = Field(default_factory=list)
    minimum_votes: int = 2
    command_window: int = 15
    command_cooldown: int = 30
    vote_permissions: str = "Everyone"
    subscriber_months: str = "SUB:3"
    override_permissions: str = "Owner"
    discord_webhook_configured: bool = False
    donotallowlist_enabled: bool = False
    donotallowlist_usernames: list[str] = Field(default_factory=list)

    @classmethod
    def from_settings(cls, settings: BroadcasterSettingsUpdate) -> "BroadcasterSettingsSnapshot":
        data = settings.model_dump()
        webhook = data.pop("discord_webhook_url", "")
        return cls(
            **data,
            discord_webhook_configured=bool(webhook),
        )


class BroadcasterSettings(BroadcasterSettingsUpdate, table=True):
    __tablename__ = "broadcaster_settings"

    broadcaster_id: str = Field(
        primary_key=True,
        foreign_key="broadcaster_installations.broadcaster_id",
    )
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
