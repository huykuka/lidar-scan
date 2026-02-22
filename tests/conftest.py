import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    from app.db.migrate import ensure_schema
    from app.db.session import init_engine

    engine = init_engine()
    ensure_schema(engine)

    from app.app import app

    with TestClient(app) as test_client:
        yield test_client
