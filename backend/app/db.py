"""The connection to the database.

By default everything is saved in a file called datovarsel.db next to
where you start the server. Set DATABASE_URL to use another database.
"""

import os

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///datovarsel.db")

# check_same_thread=False: FastAPI can answer requests on different
# threads, and SQLite only allows that if we say it's fine.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def create_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    """Give each request its own session. FastAPI calls this for us."""
    with Session(engine) as session:
        yield session
