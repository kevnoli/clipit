from urllib.parse import urlparse

from typing import Any, Annotated

from fastapi import Depends, HTTPException, Path, Request

from .app import AppServices, get_app_services


def get_session_payload(
    request: Request,
    services: Annotated[AppServices, Depends(get_app_services)],
) -> dict[str, Any]:
    token = request.cookies.get(services.session_manager.cookie_name)
    payload = services.session_manager.validate(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return payload


def get_optional_session_payload(
    request: Request,
    services: Annotated[AppServices, Depends(get_app_services)],
) -> dict[str, Any] | None:
    token = request.cookies.get(services.session_manager.cookie_name)
    return services.session_manager.validate(token)


def get_current_broadcaster_id(
    broadcaster_id: Annotated[str, Path()],
    session: Annotated[dict[str, Any], Depends(get_session_payload)],
) -> str:
    if session["broadcaster_id"] != broadcaster_id:
        raise HTTPException(status_code=403, detail="You can only manage your own broadcaster")
    return broadcaster_id


def require_csrf_protection(
    request: Request,
    services: Annotated[AppServices, Depends(get_app_services)],
    session: Annotated[dict[str, Any], Depends(get_session_payload)],
) -> dict[str, Any]:
    expected_origin = urlparse(services.settings.app_base_url).netloc
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")

    for header_value in (origin, referer):
        if not header_value:
            continue
        if urlparse(header_value).netloc != expected_origin:
            raise HTTPException(status_code=403, detail="Cross-site requests are not allowed")

    csrf_token = request.headers.get("x-csrf-token")
    if not csrf_token or csrf_token != session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="A valid CSRF token is required")
    return session
