from .auth import router as auth_router
from .broadcasters import router as broadcasters_router
from .health import router as health_router

__all__ = [
    "auth_router",
    "broadcasters_router",
    "health_router",
]
