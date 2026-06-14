from sqlmodel import create_engine, SQLModel, Session
from typing import Generator
from config import DATABASE_URL

# SQLite requires check_same_thread=False for use with FastAPI's threaded request handling.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def create_db_and_tables() -> None:
    # All model classes must be imported before create_all is called so that
    # SQLModel's metadata is aware of every table. The import below guarantees
    # this regardless of which other modules have already been loaded.
    import models  # noqa: F401 — side-effect import registers all table metadata

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
