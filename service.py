"""
Hosted service entrypoint for !Clipit
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from auth import OAuthStateStore, SessionManager, TwitchAuth
from config import BroadcasterConfig, Config
from database import Database
from logs import get_logger
from worker_manager import WorkerManager

log = get_logger(__name__)


class BroadcasterSettingsPayload(BaseModel):
    commands: list[str] = Field(default_factory=lambda: ["!clipit"])
    minimum_votes: int = 2
    command_window: int = 15
    command_cooldown: int = 30
    vote_permissions: str = "Everyone"
    subscriber_months: str = "SUB:3"
    override_permissions: str = "Owner"
    discord_webhook_url: str = ""
    donotallowlist_enabled: bool = False
    donotallowlist_usernames: list[str] = Field(default_factory=list)

    def to_runtime_config(self) -> BroadcasterConfig:
        return BroadcasterConfig.from_dict(self.model_dump())


class ClipitService:
    def __init__(self):
        self.config = Config()
        self.database = Database()
        self.auth = TwitchAuth(
            client_id=self.config.twitch_client_id,
            client_secret=self.config.twitch_client_secret,
            redirect_uri=self.config.twitch_redirect_uri,
        )
        self.session_manager = SessionManager(self.config.session_secret)
        self.state_store = OAuthStateStore()
        self.worker_manager = WorkerManager(self.config, self.database, self.auth)

    def broadcaster_snapshot(self, broadcaster_id: str) -> dict[str, Any]:
        broadcaster = self.database.get_broadcaster(broadcaster_id)
        if not broadcaster:
            raise HTTPException(status_code=404, detail="Broadcaster not found")

        settings = self.database.get_broadcaster_settings(broadcaster_id)
        worker_status = self.worker_manager.get_worker_status(broadcaster_id)
        return {
            "broadcaster_id": broadcaster["broadcaster_id"],
            "login": broadcaster["login"],
            "display_name": broadcaster.get("display_name") or broadcaster["login"],
            "enabled": bool(broadcaster["enabled"]),
            "expires_at": broadcaster["expires_at"],
            "total_clips_generated": self.database.get_total_clips_generated(broadcaster_id),
            "worker": worker_status,
            "settings": settings,
        }


def create_app() -> FastAPI:
    service = ClipitService()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.service = service
        await service.worker_manager.start_all()
        yield
        await service.worker_manager.shutdown()

    app = FastAPI(title="Clipit", lifespan=lifespan)

    def get_session_payload(request: Request) -> dict[str, Any]:
        svc: ClipitService = request.app.state.service
        token = request.cookies.get(svc.session_manager.cookie_name)
        payload = svc.session_manager.validate(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Authentication required")
        return payload

    def require_broadcaster_session(request: Request, broadcaster_id: str) -> dict[str, Any]:
        payload = get_session_payload(request)
        if payload["broadcaster_id"] != broadcaster_id:
            raise HTTPException(status_code=403, detail="You can only manage your own broadcaster")
        return payload

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        svc: ClipitService = request.app.state.service
        login_url = request.url_for("login_with_twitch")
        try:
            session = get_session_payload(request)
            account_html = (
                f'<p>Signed in as <strong>{session["login"]}</strong>.</p>'
                '<p><a href="/me">View my channel status</a> | '
                '<a href="/auth/logout">Log out</a></p>'
            )
        except HTTPException:
            account_html = f'<p><a href="{login_url}">Connect your Twitch channel</a></p>'

        return HTMLResponse(
            f"""
            <html>
                <head><title>Clipit</title></head>
                <body>
                    <h1>Clipit</h1>
                    <p>Hosted Twitch clip voting for multiple broadcasters.</p>
                    <p>Connected broadcasters: {svc.database.get_connected_broadcaster_count()}</p>
                    {account_html}
                    <p>Public endpoint: <code>/health</code></p>
                </body>
            </html>
            """
        )

    @app.get("/health")
    async def health(request: Request):
        svc: ClipitService = request.app.state.service
        return {
            "status": "ok",
            "connected_broadcasters": svc.database.get_connected_broadcaster_count(),
            "running_workers": svc.worker_manager.connected_count(),
        }

    @app.get("/me")
    async def get_me(request: Request):
        svc: ClipitService = request.app.state.service
        session = get_session_payload(request)
        return svc.broadcaster_snapshot(session["broadcaster_id"])

    @app.get("/broadcasters")
    async def list_broadcasters(request: Request):
        svc: ClipitService = request.app.state.service
        session = get_session_payload(request)
        return [svc.broadcaster_snapshot(session["broadcaster_id"])]

    @app.get("/broadcasters/{broadcaster_id}")
    async def get_broadcaster(request: Request, broadcaster_id: str):
        svc: ClipitService = request.app.state.service
        require_broadcaster_session(request, broadcaster_id)
        return svc.broadcaster_snapshot(broadcaster_id)

    @app.put("/broadcasters/{broadcaster_id}/settings")
    async def update_broadcaster_settings(
        request: Request,
        broadcaster_id: str,
        payload: BroadcasterSettingsPayload,
    ):
        svc: ClipitService = request.app.state.service
        require_broadcaster_session(request, broadcaster_id)
        broadcaster = svc.database.get_broadcaster(broadcaster_id)
        if not broadcaster:
            raise HTTPException(status_code=404, detail="Broadcaster not found")

        settings = await svc.worker_manager.update_broadcaster_settings(
            broadcaster_id,
            payload.to_runtime_config(),
        )
        return {
            "status": "updated",
            "broadcaster_id": broadcaster_id,
            "settings": settings,
        }

    @app.post("/broadcasters/{broadcaster_id}/disable")
    async def disable_broadcaster(request: Request, broadcaster_id: str):
        svc: ClipitService = request.app.state.service
        require_broadcaster_session(request, broadcaster_id)
        if not svc.database.get_broadcaster(broadcaster_id):
            raise HTTPException(status_code=404, detail="Broadcaster not found")
        await svc.worker_manager.disable_broadcaster(broadcaster_id)
        return {"status": "disabled", "broadcaster_id": broadcaster_id}

    @app.post("/broadcasters/{broadcaster_id}/enable")
    async def enable_broadcaster(request: Request, broadcaster_id: str):
        svc: ClipitService = request.app.state.service
        require_broadcaster_session(request, broadcaster_id)
        if not svc.database.get_broadcaster(broadcaster_id):
            raise HTTPException(status_code=404, detail="Broadcaster not found")
        await svc.worker_manager.enable_broadcaster(broadcaster_id)
        return svc.broadcaster_snapshot(broadcaster_id)

    @app.delete("/broadcasters/{broadcaster_id}")
    async def disconnect_broadcaster(request: Request, broadcaster_id: str):
        svc: ClipitService = request.app.state.service
        require_broadcaster_session(request, broadcaster_id)
        if not svc.database.get_broadcaster(broadcaster_id):
            raise HTTPException(status_code=404, detail="Broadcaster not found")
        await svc.worker_manager.disconnect_broadcaster(broadcaster_id)
        response = RedirectResponse(url="/", status_code=303)
        response.delete_cookie(svc.session_manager.cookie_name)
        return response

    @app.get("/auth/twitch/login", name="login_with_twitch")
    async def login_with_twitch(request: Request):
        svc: ClipitService = request.app.state.service
        state = svc.state_store.issue()
        auth_url = svc.auth.get_auth_url(state=state)
        return RedirectResponse(auth_url)

    @app.get("/auth/logout")
    async def logout(request: Request):
        svc: ClipitService = request.app.state.service
        response = RedirectResponse(url="/", status_code=303)
        response.delete_cookie(svc.session_manager.cookie_name)
        return response

    @app.get(service.config.twitch_redirect_path, response_class=HTMLResponse)
    async def twitch_callback(
        request: Request,
        code: str | None = Query(default=None),
        state: str | None = Query(default=None),
        error: str | None = Query(default=None),
        error_description: str | None = Query(default=None),
    ):
        svc: ClipitService = request.app.state.service

        if error:
            return HTMLResponse(
                f"<h1>Twitch authentication failed</h1><p>{error}: {error_description or ''}</p>",
                status_code=400,
            )

        if not svc.state_store.validate(state):
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

        if not code:
            raise HTTPException(status_code=400, detail="Missing Twitch authorization code")

        tokens = await svc.auth.exchange_code_for_tokens(code)
        user_info = await svc.auth.get_user_info(tokens["access_token"])
        if not user_info or "id" not in user_info or "login" not in user_info:
            raise HTTPException(
                status_code=400,
                detail="Could not determine Twitch broadcaster identity",
            )

        broadcaster_id = user_info["id"]
        login = user_info["login"].lower()
        display_name = user_info.get("display_name") or login

        svc.database.save_broadcaster(
            broadcaster_id=broadcaster_id,
            login=login,
            display_name=display_name,
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            expires_at=tokens["expires_at"],
            enabled=True,
        )
        svc.database.ensure_broadcaster_settings(
            broadcaster_id,
            svc.config.default_broadcaster_config(),
        )
        await svc.worker_manager.start_or_restart_broadcaster(broadcaster_id)

        session_token = svc.session_manager.issue(broadcaster_id=broadcaster_id, login=login)
        response = HTMLResponse(
            f"""
            <html>
                <head><title>Clipit Connected</title></head>
                <body>
                    <h1>Channel connected</h1>
                    <p><strong>{display_name}</strong> is now connected to this Clipit instance.</p>
                    <p>Your channel bot will join <code>{login}</code> and create clips using your Twitch authorization.</p>
                    <p>You are now signed in. Open <a href=\"/me\">/me</a> to inspect or update your channel.</p>
                </body>
            </html>
            """
        )
        response.set_cookie(
            key=svc.session_manager.cookie_name,
            value=session_token,
            httponly=True,
            samesite="lax",
            secure=svc.config.session_cookie_secure,
            max_age=svc.session_manager.max_age_seconds,
        )

        log.info("Broadcaster connected via hosted OAuth and signed in: %s", login)
        return response

    return app
