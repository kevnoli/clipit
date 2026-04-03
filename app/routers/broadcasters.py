from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel

from app.dependencies import (
    AppServices,
    get_app_services,
    get_current_broadcaster_id,
    get_session_payload,
    require_csrf_protection,
)
from app.models import (
    BroadcasterSettingsPayload,
    BroadcasterSettingsSnapshot,
    BroadcasterSnapshot,
    WorkerStatus,
)

router = APIRouter(tags=["broadcasters"])


class SettingsUpdateResponse(SQLModel):
    status: str
    broadcaster_id: str
    settings: BroadcasterSettingsSnapshot


class ActionResponse(SQLModel):
    status: str
    broadcaster_id: str


def build_broadcaster_snapshot(
    services: AppServices,
    broadcaster_id: str,
) -> BroadcasterSnapshot:
    broadcaster = services.database.get_broadcaster(broadcaster_id)
    if broadcaster is None:
        raise HTTPException(status_code=404, detail="Broadcaster not found")

    settings = services.database.get_broadcaster_settings(broadcaster_id)
    snapshot = BroadcasterSnapshot(
        broadcaster_id=broadcaster.broadcaster_id,
        login=broadcaster.login,
        display_name=broadcaster.display_name,
        enabled=broadcaster.enabled,
        expires_at=broadcaster.expires_at,
        worker=WorkerStatus(
            **services.worker_manager.get_worker_status(broadcaster_id),
            worker_error=broadcaster.worker_error,
        ),
        settings=BroadcasterSettingsSnapshot.from_settings(settings) if settings else None,
    )
    return snapshot


@router.get("/me", response_model=BroadcasterSnapshot)
async def get_me(
    services: Annotated[AppServices, Depends(get_app_services)],
    session: Annotated[dict[str, object], Depends(get_session_payload)],
):
    return build_broadcaster_snapshot(services, str(session["broadcaster_id"]))


@router.get("/broadcasters", response_model=list[BroadcasterSnapshot])
async def list_broadcasters(
    services: Annotated[AppServices, Depends(get_app_services)],
    session: Annotated[dict[str, object], Depends(get_session_payload)],
):
    return [build_broadcaster_snapshot(services, str(session["broadcaster_id"]))]


@router.get("/broadcasters/{broadcaster_id}", response_model=BroadcasterSnapshot)
async def get_broadcaster(
    services: Annotated[AppServices, Depends(get_app_services)],
    broadcaster_id: Annotated[str, Depends(get_current_broadcaster_id)],
):
    return build_broadcaster_snapshot(services, broadcaster_id)


@router.put("/broadcasters/{broadcaster_id}/settings", response_model=SettingsUpdateResponse)
async def update_broadcaster_settings(
    payload: BroadcasterSettingsPayload,
    services: Annotated[AppServices, Depends(get_app_services)],
    session: Annotated[dict[str, object], Depends(require_csrf_protection)],
    broadcaster_id: Annotated[str, Depends(get_current_broadcaster_id)],
):
    del session
    broadcaster = services.database.get_broadcaster(broadcaster_id)
    if broadcaster is None:
        raise HTTPException(status_code=404, detail="Broadcaster not found")

    existing_settings = services.database.get_broadcaster_settings(broadcaster_id)
    settings = await services.worker_manager.update_broadcaster_settings(
        broadcaster_id,
        payload.to_settings_update(existing_settings),
    )
    return SettingsUpdateResponse(
        status="updated",
        broadcaster_id=broadcaster_id,
        settings=BroadcasterSettingsSnapshot.from_settings(settings),
    )


@router.post("/broadcasters/{broadcaster_id}/disable", response_model=ActionResponse)
async def disable_broadcaster(
    services: Annotated[AppServices, Depends(get_app_services)],
    session: Annotated[dict[str, object], Depends(require_csrf_protection)],
    broadcaster_id: Annotated[str, Depends(get_current_broadcaster_id)],
):
    del session
    if services.database.get_broadcaster(broadcaster_id) is None:
        raise HTTPException(status_code=404, detail="Broadcaster not found")

    await services.worker_manager.disable_broadcaster(broadcaster_id)
    return ActionResponse(status="disabled", broadcaster_id=broadcaster_id)


@router.post("/broadcasters/{broadcaster_id}/enable", response_model=BroadcasterSnapshot)
async def enable_broadcaster(
    services: Annotated[AppServices, Depends(get_app_services)],
    session: Annotated[dict[str, object], Depends(require_csrf_protection)],
    broadcaster_id: Annotated[str, Depends(get_current_broadcaster_id)],
):
    del session
    if services.database.get_broadcaster(broadcaster_id) is None:
        raise HTTPException(status_code=404, detail="Broadcaster not found")

    await services.worker_manager.enable_broadcaster(broadcaster_id)
    return build_broadcaster_snapshot(services, broadcaster_id)


@router.delete("/broadcasters/{broadcaster_id}")
async def disconnect_broadcaster(
    request: Request,
    services: Annotated[AppServices, Depends(get_app_services)],
    session: Annotated[dict[str, object], Depends(require_csrf_protection)],
    broadcaster_id: Annotated[str, Depends(get_current_broadcaster_id)],
):
    del session
    if services.database.get_broadcaster(broadcaster_id) is None:
        raise HTTPException(status_code=404, detail="Broadcaster not found")

    await services.worker_manager.disconnect_broadcaster(broadcaster_id)
    response = JSONResponse(
        ActionResponse(status="disconnected", broadcaster_id=broadcaster_id).model_dump()
    )
    services.session_manager.invalidate(
        request.cookies.get(services.session_manager.cookie_name)
    )
    response.delete_cookie(services.session_manager.cookie_name)
    response.delete_cookie(services.settings.csrf_cookie_name)
    return response
