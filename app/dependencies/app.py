from dataclasses import dataclass

from fastapi import Request

from app.core.config import Settings
from app.core.security import OAuthStateStore, SecretBox, SessionManager, TwitchAuth
from app.db import Database
from app.runtime.worker_manager import WorkerManager


@dataclass(slots=True)
class AppServices:
    settings: Settings
    database: Database
    auth: TwitchAuth
    session_manager: SessionManager
    state_store: OAuthStateStore
    worker_manager: WorkerManager


def build_app_services(settings: Settings) -> AppServices:
    secret_box = SecretBox(settings.secret_encryption_key)
    database = Database(settings.database_url, secret_box=secret_box)
    auth = TwitchAuth(
        client_id=settings.twitch_client_id,
        client_secret=settings.twitch_client_secret,
        redirect_uri=settings.twitch_redirect_uri,
    )
    session_manager = SessionManager(database, settings.session_secret)
    state_store = OAuthStateStore()
    worker_manager = WorkerManager(settings, database, auth, session_manager)
    return AppServices(
        settings=settings,
        database=database,
        auth=auth,
        session_manager=session_manager,
        state_store=state_store,
        worker_manager=worker_manager,
    )


def get_app_services(request: Request) -> AppServices:
    return request.app.state.services
