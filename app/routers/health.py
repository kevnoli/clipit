from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import SQLModel

from app.dependencies import AppServices, get_app_services

router = APIRouter(tags=["health"])


class HealthResponse(SQLModel):
    status: str
    connected_broadcasters: int
    running_workers: int


@router.get("/health", response_model=HealthResponse)
async def health(
    services: Annotated[AppServices, Depends(get_app_services)],
):
    return HealthResponse(
        status="ok",
        connected_broadcasters=services.database.get_connected_broadcaster_count(),
        running_workers=services.worker_manager.connected_count(),
    )
