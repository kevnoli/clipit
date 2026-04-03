import secrets
from typing import Annotated
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from app.dependencies import AppServices, get_app_services, require_csrf_protection
from app.models import BroadcasterSettingsUpdate

router = APIRouter(prefix="/auth", tags=["auth"])


def _clear_auth_cookies(response: RedirectResponse, services: AppServices):
    response.delete_cookie(services.session_manager.cookie_name)
    response.delete_cookie(services.settings.csrf_cookie_name)
    response.delete_cookie(services.settings.oauth_state_cookie_name)


@router.get("/twitch/login", name="login_with_twitch")
async def login_with_twitch(
    services: Annotated[AppServices, Depends(get_app_services)],
):
    browser_binding = secrets.token_urlsafe(32)
    state = services.state_store.issue(browser_binding)
    auth_url = services.auth.get_auth_url(state=state)
    response = RedirectResponse(auth_url)
    response.set_cookie(
        key=services.settings.oauth_state_cookie_name,
        value=browser_binding,
        httponly=True,
        samesite="lax",
        secure=services.settings.session_cookie_secure,
        max_age=600,
    )
    return response


@router.post("/logout")
async def logout(
    request: Request,
    services: Annotated[AppServices, Depends(get_app_services)],
    session: Annotated[dict[str, object], Depends(require_csrf_protection)],
):
    del session
    services.session_manager.invalidate(
        request.cookies.get(services.session_manager.cookie_name)
    )
    response = RedirectResponse(url="/", status_code=303)
    _clear_auth_cookies(response, services)
    return response


@router.get("/twitch/callback")
async def twitch_callback(
    request: Request,
    services: Annotated[AppServices, Depends(get_app_services)],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    if error:
        message = quote_plus(error_description or error)
        response = RedirectResponse(url=f"/?auth=error&message={message}", status_code=303)
        _clear_auth_cookies(response, services)
        return response

    browser_binding = request.cookies.get(services.settings.oauth_state_cookie_name)
    if not services.state_store.validate(state, browser_binding):
        response = RedirectResponse(
            url="/?auth=error&message=Invalid+or+expired+OAuth+state",
            status_code=303,
        )
        _clear_auth_cookies(response, services)
        return response

    if not code:
        response = RedirectResponse(
            url="/?auth=error&message=Missing+Twitch+authorization+code",
            status_code=303,
        )
        _clear_auth_cookies(response, services)
        return response

    try:
        tokens = await services.auth.exchange_code_for_tokens(code)
        user_info = await services.auth.get_user_info(tokens["access_token"])
    except Exception:
        response = RedirectResponse(
            url="/?auth=error&message=Could+not+complete+Twitch+sign-in",
            status_code=303,
        )
        _clear_auth_cookies(response, services)
        return response

    if not user_info or "id" not in user_info or "login" not in user_info:
        response = RedirectResponse(
            url="/?auth=error&message=Could+not+determine+the+broadcaster+identity",
            status_code=303,
        )
        _clear_auth_cookies(response, services)
        return response

    broadcaster_id = user_info["id"]
    login = user_info["login"].lower()
    display_name = user_info.get("display_name") or login

    services.database.save_broadcaster(
        broadcaster_id=broadcaster_id,
        login=login,
        display_name=display_name,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_at=tokens["expires_at"],
        enabled=True,
    )
    services.database.ensure_broadcaster_settings(
        broadcaster_id,
        BroadcasterSettingsUpdate(),
    )
    await services.worker_manager.start_or_restart_broadcaster(broadcaster_id)

    session_token, csrf_token = services.session_manager.issue(
        broadcaster_id=broadcaster_id,
        login=login,
    )
    response = RedirectResponse(
        url=f"/?connected=1&channel={quote_plus(display_name)}",
        status_code=303,
    )
    response.set_cookie(
        key=services.session_manager.cookie_name,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=services.settings.session_cookie_secure,
        max_age=services.session_manager.max_age_seconds,
    )
    response.set_cookie(
        key=services.settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=services.settings.session_cookie_secure,
        max_age=services.session_manager.max_age_seconds,
    )
    response.delete_cookie(services.settings.oauth_state_cookie_name)
    return response
