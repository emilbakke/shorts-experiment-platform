import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from .local_db_defaults import default_database_urls

_default_content_url, _default_behavior_url, _default_database_url = default_database_urls()
DATABASE_URL = os.getenv("DATABASE_URL", _default_database_url)
CONTENT_DATABASE_URL = os.getenv("CONTENT_DATABASE_URL", _default_content_url if "DATABASE_URL" not in os.environ else DATABASE_URL)
BEHAVIOR_DATABASE_URL = os.getenv("BEHAVIOR_DATABASE_URL", _default_behavior_url if "DATABASE_URL" not in os.environ else DATABASE_URL)


def _connect_args(url: str) -> dict:
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {"connect_args": _connect_args(url), "future": True}
    if url.startswith("postgresql"):
        kwargs.update(
            {
                "pool_pre_ping": True,
                "pool_size": int(os.getenv("VIEWTUBE_BEHAVIOR_DB_POOL_SIZE", "5")),
                "max_overflow": int(os.getenv("VIEWTUBE_BEHAVIOR_DB_MAX_OVERFLOW", "10")),
                "pool_recycle": int(os.getenv("VIEWTUBE_BEHAVIOR_DB_POOL_RECYCLE_SECONDS", "1800")),
            }
        )
    return kwargs


content_engine = create_engine(CONTENT_DATABASE_URL, **_engine_kwargs(CONTENT_DATABASE_URL))
behavior_engine = create_engine(BEHAVIOR_DATABASE_URL, **_engine_kwargs(BEHAVIOR_DATABASE_URL))

ContentSessionLocal = sessionmaker(bind=content_engine, autoflush=False, autocommit=False, future=True)
BehaviorSessionLocal = sessionmaker(bind=behavior_engine, autoflush=False, autocommit=False, future=True)

# Backwards-compatibility aliases for legacy content/video scripts.
engine = content_engine
SessionLocal = ContentSessionLocal

Base = declarative_base()


def get_content_db():
    db = ContentSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_behavior_db():
    db = BehaviorSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Backwards compatibility for older imports that expect a single DB dependency.
get_db = get_content_db
