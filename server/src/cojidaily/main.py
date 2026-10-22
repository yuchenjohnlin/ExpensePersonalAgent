"""The HTTP app: `uvicorn cojidaily.main:create_app --factory`.

It mounts each module's router; the modules never import each other's routers.
"""
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from .auth import api as auth
from .auth import router as auth_routes
from .ledger import router as ledger_routes
from .photos import router as photo_routes
from .receipts import router as receipt_routes
from .platform import errors, logs
from .platform.blobstore import BlobStore
from .platform.db import make_engine, make_sessions
from .platform.settings import Settings

health = APIRouter(prefix="/api")


@health.get("/health")
def healthy() -> dict:
    return {"ok": True}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    logs.configure()
    engine = make_engine(settings.database_url, settings.db_pool_size)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(title="CojiDaily", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json",
                  redoc_url=None)
    app.state.settings = settings
    app.state.sessions = make_sessions(engine)
    app.state.blobs = BlobStore(settings.blob_root)
    errors.install(app)
    # Every write to /api/ passes the CSRF check before any route runs.
    app.add_middleware(auth.CsrfMiddleware, trusted_origins=settings.csrf_trusted_origins)
    for router in (health, auth_routes.router, ledger_routes.router, photo_routes.router,
                   receipt_routes.router):
        app.include_router(router)
    return app
