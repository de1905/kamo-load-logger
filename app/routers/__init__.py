"""API routers."""

from app.routers.status import router as status_router
from app.routers.load import router as load_router
from app.routers.substations import router as substations_router
from app.routers.export import router as export_router
from app.routers.backups import router as backups_router

__all__ = ["status_router", "load_router", "substations_router", "export_router", "backups_router"]
