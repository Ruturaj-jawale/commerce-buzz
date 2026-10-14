import pytest

from app.db.database import init_db


@pytest.fixture(scope="session", autouse=True)
def initialize_database():
    init_db()
    yield
