import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel, create_engine

import app.models  # noqa: F401
from app.core.config import Settings
from app.dependencies import build_app_services
from app.models import BroadcasterSettingsUpdate
from app.routers import auth_router, broadcasters_router, health_router


def build_test_app(tmp_path: Path):
    database_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{database_path}")
    SQLModel.metadata.create_all(engine)

    settings = Settings.model_validate(
        {
            "app_name": "Clipit Test",
            "app_base_url": "https://clipit.example.test",
            "session_secret": "session-secret-for-tests",
            "secret_encryption_key": "encryption-secret-for-tests",
            "twitch_client_id": "client-id",
            "twitch_client_secret": "client-secret",
            "database_url": f"sqlite:///{database_path}",
            "cors_origins": [],
        }
    )
    services = build_app_services(settings)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.services = services
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(broadcasters_router, prefix="/api")
    app.mount("/", StaticFiles(directory=Path("app/static"), html=True), name="site")
    return app


def create_session(client: TestClient, app, broadcaster_id: str, login: str) -> tuple[str, str]:
    services = app.state.services
    services.database.save_broadcaster(
        broadcaster_id=broadcaster_id,
        login=login,
        display_name=login.title(),
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=9999999999,
    )
    services.database.ensure_broadcaster_settings(
        broadcaster_id,
        BroadcasterSettingsUpdate(discord_webhook_url="https://discord.example/webhook"),
    )
    session_token, csrf_token = services.session_manager.issue(broadcaster_id, login)
    client.cookies.set(services.session_manager.cookie_name, session_token)
    client.cookies.set(services.settings.csrf_cookie_name, csrf_token)
    return session_token, csrf_token


class FakeWorker:
    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True

    def is_running(self) -> bool:
        return True


def test_runtime_failure_disables_broadcaster_and_invalidates_session(tmp_path: Path):
    app = build_test_app(tmp_path)
    with TestClient(app) as client:
        session_token, _csrf_token = create_session(client, app, "123", "owner")
        services = app.state.services
        fake_worker = FakeWorker()
        services.worker_manager._workers["123"] = fake_worker

        response = client.get("/api/me")
        assert response.status_code == 200

        asyncio.run(
            services.worker_manager.handle_runtime_failure(
                "123",
                'channel "owner" could not be joined',
            )
        )

        broadcaster = services.database.get_broadcaster("123")
        assert broadcaster is not None
        assert broadcaster.enabled is False
        assert broadcaster.worker_error == 'channel "owner" could not be joined'
        assert fake_worker.stopped is True
        assert services.worker_manager.get_worker_status("123") == {
            "worker_present": False,
            "worker_running": False,
        }
        assert services.database.get_session(session_token) is not None

        response = client.get("/api/me")
        assert response.status_code == 200
        payload = response.json()
        assert payload["worker"]["worker_error"] == 'channel "owner" could not be joined'
