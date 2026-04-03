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


def test_me_requires_authentication(tmp_path: Path):
    app = build_test_app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/me")
    assert response.status_code == 401


def test_broadcaster_routes_enforce_ownership(tmp_path: Path):
    app = build_test_app(tmp_path)
    with TestClient(app) as client:
        create_session(client, app, "123", "owner")
        response = client.get("/api/broadcasters/456")
    assert response.status_code == 403


def test_me_does_not_leak_webhook_or_tokens(tmp_path: Path):
    app = build_test_app(tmp_path)
    with TestClient(app) as client:
        create_session(client, app, "123", "owner")
        response = client.get("/api/me")
    assert response.status_code == 200
    payload = response.json()
    assert "access_token" not in payload
    assert "refresh_token" not in payload
    assert "discord_webhook_url" not in payload["settings"]
    assert payload["settings"]["discord_webhook_configured"] is True


def test_logout_requires_csrf_token(tmp_path: Path):
    app = build_test_app(tmp_path)
    with TestClient(app) as client:
        create_session(client, app, "123", "owner")
        response = client.post("/api/auth/logout")
    assert response.status_code == 403
