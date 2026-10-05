from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings


def create_db_engine(settings: Settings) -> Engine:
    database_url = settings.database_url.get_secret_value()
    return create_engine(
        database_url,
        connect_args={"options": "-c timezone=UTC"}
        if database_url.startswith("postgresql")
        else {},
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
    )


def create_session_factory(
    engine: Engine, *, settings: Settings | None = None
) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        info={"settings": settings} if settings is not None else {},
    )
