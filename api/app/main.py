from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.envelope import install_handlers, ok

health_router = APIRouter()


@health_router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return ok({"status": "ok", "db": "ok"})


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
    app.include_router(health_router, prefix="/api")
    return app


app = create_app()
