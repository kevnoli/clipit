"""
Broadcaster worker management for hosted !Clipit
"""

import asyncio
import contextlib
import time
from typing import Awaitable, Callable

from app.core.config import Settings
from app.core.logs import get_logger
from app.core.security import TwitchAuth
from app.db import Database
from app.integrations.twitch_api import TwitchAPI
from app.models import BroadcasterInstallation, BroadcasterSettings, BroadcasterSettingsUpdate
from app.runtime.bot import ClipitBot

log = get_logger(__name__)

ApiFactory = Callable[[], Awaitable[TwitchAPI]]


class BroadcasterWorker:
    def __init__(
        self,
        settings: Settings,
        runtime_config: BroadcasterSettings,
        database: Database,
        installation: BroadcasterInstallation,
        api_factory: ApiFactory,
    ):
        self.settings = settings
        self.runtime_config = runtime_config
        self.database = database
        self.installation = installation
        self.api_factory = api_factory
        self.bot: ClipitBot | None = None
        self.task: asyncio.Task | None = None

    async def start(self):
        if self.task and not self.task.done():
            log.debug("Worker already running for %s", self.installation.login)
            return

        self.bot = ClipitBot(
            config=self.runtime_config,
            database=self.database,
            access_token=self.installation.access_token,
            broadcaster_id=self.installation.broadcaster_id,
            bot_id=self.installation.broadcaster_id,
            twitch_client_id=self.settings.twitch_client_id,
            twitch_client_secret=self.settings.twitch_client_secret,
            bot_username=self.installation.login,
            broadcaster_name=self.installation.login,
            api_factory=self.api_factory,
        )
        self.task = asyncio.create_task(
            self._run(), name=f"clipit:{self.installation.login}"
        )

    async def _run(self):
        assert self.bot is not None
        try:
            await self.bot.start()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error(
                "Worker for %s stopped unexpectedly: %s",
                self.installation.login,
                exc,
                exc_info=True,
            )

    async def stop(self):
        if self.bot is not None:
            with contextlib.suppress(Exception):
                await self.bot.close()

        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task

        self.bot = None
        self.task = None

    def is_running(self) -> bool:
        return bool(self.task and not self.task.done())


class WorkerManager:
    def __init__(self, settings: Settings, database: Database, auth: TwitchAuth):
        self.settings = settings
        self.database = database
        self.auth = auth
        self._workers: dict[str, BroadcasterWorker] = {}
        self._lock = asyncio.Lock()

    async def start_all(self):
        for installation in self.database.get_enabled_broadcasters():
            await self.start_or_restart_broadcaster(
                installation.broadcaster_id,
                installation=installation,
            )

    async def shutdown(self):
        async with self._lock:
            broadcaster_ids = list(self._workers)
        for broadcaster_id in broadcaster_ids:
            await self.stop_broadcaster(broadcaster_id)

    async def start_or_restart_broadcaster(
        self,
        broadcaster_id: str,
        installation: BroadcasterInstallation | None = None,
    ) -> BroadcasterInstallation:
        installation = await self.ensure_valid_installation(broadcaster_id, installation)
        if installation is None:
            raise RuntimeError(f"Broadcaster {broadcaster_id} is not available")

        runtime_config = self.database.ensure_broadcaster_settings(
            broadcaster_id,
            BroadcasterSettingsUpdate(),
        )

        async with self._lock:
            existing_worker = self._workers.get(broadcaster_id)
            if existing_worker:
                await existing_worker.stop()

            worker = BroadcasterWorker(
                settings=self.settings,
                runtime_config=runtime_config,
                database=self.database,
                installation=installation,
                api_factory=lambda broadcaster_id=broadcaster_id: self.get_api_client(
                    broadcaster_id
                ),
            )
            self._workers[broadcaster_id] = worker

        await worker.start()
        log.info("Broadcaster worker running for %s", installation.login)
        return installation

    async def stop_broadcaster(self, broadcaster_id: str):
        async with self._lock:
            worker = self._workers.pop(broadcaster_id, None)

        if worker:
            await worker.stop()
            log.info("Broadcaster worker stopped for %s", broadcaster_id)

    async def disable_broadcaster(self, broadcaster_id: str):
        self.database.set_broadcaster_enabled(broadcaster_id, False)
        await self.stop_broadcaster(broadcaster_id)

    async def enable_broadcaster(self, broadcaster_id: str) -> BroadcasterInstallation:
        self.database.set_broadcaster_enabled(broadcaster_id, True)
        return await self.start_or_restart_broadcaster(broadcaster_id)

    async def disconnect_broadcaster(self, broadcaster_id: str):
        await self.stop_broadcaster(broadcaster_id)
        self.database.delete_broadcaster(broadcaster_id)

    async def update_broadcaster_settings(
        self,
        broadcaster_id: str,
        runtime_config: BroadcasterSettingsUpdate,
    ) -> BroadcasterSettings:
        settings = self.database.save_broadcaster_settings(broadcaster_id, runtime_config)
        installation = self.database.get_broadcaster(broadcaster_id)
        if installation and installation.enabled:
            await self.start_or_restart_broadcaster(broadcaster_id, installation=installation)
        return settings

    async def ensure_valid_installation(
        self,
        broadcaster_id: str,
        installation: BroadcasterInstallation | None = None,
    ) -> BroadcasterInstallation | None:
        record = installation or self.database.get_broadcaster(broadcaster_id)
        if record is None or not record.enabled:
            return None

        current_time = int(time.time())
        if current_time < int(record.expires_at) - 300:
            return record

        try:
            tokens = await self.auth.refresh_access_token(record.refresh_token)
        except Exception:
            log.error(
                "Failed to refresh Twitch token for %s; disabling broadcaster",
                record.login,
                exc_info=True,
            )
            await self.disable_broadcaster(broadcaster_id)
            return None

        self.database.save_broadcaster(
            broadcaster_id=record.broadcaster_id,
            login=record.login,
            display_name=record.display_name,
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            expires_at=tokens["expires_at"],
            enabled=True,
        )
        return self.database.get_broadcaster(broadcaster_id)

    async def get_api_client(self, broadcaster_id: str) -> TwitchAPI:
        record = await self.ensure_valid_installation(broadcaster_id)
        if record is None:
            raise RuntimeError(f"Broadcaster {broadcaster_id} is not enabled")
        return TwitchAPI(self.settings.twitch_client_id, record.access_token)

    def connected_count(self) -> int:
        return len(self._workers)

    def get_worker_status(self, broadcaster_id: str) -> dict[str, bool]:
        worker = self._workers.get(broadcaster_id)
        return {
            "worker_present": worker is not None,
            "worker_running": worker.is_running() if worker else False,
        }
