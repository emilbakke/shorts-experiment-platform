from backend.app.database import Base, ContentSessionLocal, content_engine
from backend.app import models  # noqa: F401 - imported so SQLAlchemy registers tables
from backend.app.seed import seed_database


def main() -> None:
    Base.metadata.create_all(bind=content_engine, tables=[model.__table__ for model in models.CONTENT_MODELS])
    db = ContentSessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    print("seeded videos")


if __name__ == "__main__":
    main()
