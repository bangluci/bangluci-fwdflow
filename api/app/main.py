from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.router import router as audit_router
from app.auth.deps import CsrfMiddleware
from app.auth.router import router as auth_router
from app.catalog.router import router as catalog_router
from app.config import get_settings
from app.db import get_db
from app.envelope import install_handlers, ok

health_router = APIRouter()


@health_router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return ok({"status": "ok", "db": "ok"})


ROUTERS = [health_router, auth_router, audit_router, catalog_router]


def create_app() -> FastAPI:
    settings = get_settings()
    docs = settings.app_env != "prod"
    app = FastAPI(
        title="FwdFlow API",
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    install_handlers(app)
    app.add_middleware(CsrfMiddleware)
    for router in ROUTERS:
        app.include_router(router, prefix="/api")
    return app


app = create_app()
