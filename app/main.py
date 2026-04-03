from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.logs import init_logging
from app.dependencies import build_app_services
from app.routers import auth_router, broadcasters_router, health_router

STATIC_DIR = Path(__file__).resolve().parent / "static"

def create_app(settings=None) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_runtime_settings()
    init_logging(level=settings.log_level)
    services = build_app_services(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.services = services
        await services.worker_manager.start_all()
        yield
        await services.worker_manager.shutdown()

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

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
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="site")
    return app


app = create_app()


def main():
    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
