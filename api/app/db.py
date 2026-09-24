from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()
engine: Engine = create_engine(_settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _pin_as_of(session: Session, transaction, connection) -> None:
    """APP_TODAY (test/e2e) cố định ngày tham chiếu cho nlq_today() trong mọi transaction."""
    today = get_settings().app_today
    if today is not None:
        connection.execute(text("SELECT set_config('app.as_of', :d, true)"), {"d": today.isoformat()})


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
