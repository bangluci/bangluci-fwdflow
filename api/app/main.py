from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.extraction.router import router as extraction_router
from app.ai.hs import embed
from app.ai.hs.router import router as hs_router
from app.ai.nlq.router import router as nlq_router
from app.ai.router import router as ai_router
from app.audit.router import router as audit_router
from app.auth.deps import CsrfMiddleware
from app.auth.router import router as auth_router
from app.catalog.router import router as catalog_router
from app.config import get_settings
from app.db import get_db
from app.documents.router import router as documents_router
from app.driver.router import router as driver_router
from app.envelope import install_handlers, ok
from app.finance.router import router as finance_router
from app.freetime.router import router as freetime_router
from app.lastmile.public_router import router as public_router
from app.lastmile.router import router as last_mile_router
from app.notifications import models as _notification_models  # noqa: F401  đăng ký AUDIT_FIELDS cho bộ lọc audit
from app.reports.router import router as reports_router
from app.shipments.containers_router import router as containers_router
from app.shipments.portal_router import router as portal_router
from app.shipments.router import router as shipments_router
from app.trucking.router import router as trucking_router

health_router = APIRouter()


@health_router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return ok({"status": "ok", "db": "ok"})


ROUTERS = [health_router, auth_router, audit_router, catalog_router, shipments_router, containers_router,
           documents_router, ai_router, extraction_router, hs_router, nlq_router, freetime_router, trucking_router,
           driver_router, last_mile_router, public_router,
           finance_router, reports_router, portal_router]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Nạp bge-m3 ở luồng nền khi EMBED_PRELOAD bật; chưa nạp xong thì gợi ý mã HS chạy bản rút gọn."""
    if get_settings().embed_preload:
        embed.start_background_load()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    docs = settings.app_env != "prod"
    app = FastAPI(
        lifespan=lifespan,
        title="FwdFlow API",
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    install_handlers(app)
    app.add_middleware(CsrfMiddleware)

    @app.middleware("http")
    async def public_headers(request: Request, call_next):
        """Mọi phản hồi của `/api/public/` (cả lỗi) không cho lập chỉ mục, không gửi referrer, không cache."""
        response = await call_next(request)
        if request.url.path.startswith("/api/public/"):
            response.headers["X-Robots-Tag"] = "noindex"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Cache-Control"] = "no-store"
        return response

    for router in ROUTERS:
        app.include_router(router, prefix="/api")
    return app


app = create_app()
