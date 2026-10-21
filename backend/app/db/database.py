"""SQLAlchemy engine and session factory. Swap DATABASE_URL to use PostgreSQL later."""

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import Base

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    # Lightweight schema compatibility upgrade for databases created before new columns were added.
    try:
        inspector = inspect(engine)
        is_pg = not settings.database_url.startswith("sqlite")
        with engine.begin() as connection:
            for table in Base.metadata.tables.values():
                if table.name not in inspector.get_table_names():
                    continue
                existing = {column["name"] for column in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name in existing:
                        continue
                    ddl_type = column.type.compile(dialect=engine.dialect)
                    default = ""
                    if column.default is not None and hasattr(column.default, "arg"):
                        arg = column.default.arg
                        if isinstance(arg, str):
                            default = f" DEFAULT '{arg}'"
                        elif isinstance(arg, bool):
                            default = f" DEFAULT {int(arg)}"
                        elif isinstance(arg, (int, float)):
                            default = f" DEFAULT {arg}"
                    try:
                        if is_pg:
                            connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN IF NOT EXISTS {column.name} {ddl_type}{default}"))
                        else:
                            connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl_type}{default}"))
                    except Exception:
                        pass
    except Exception:
        pass
