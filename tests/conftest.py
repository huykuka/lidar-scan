import pytest
from fastapi.testclient import TestClient


def pytest_configure(config: pytest.Config) -> None:
    """Register custom pytest marks."""
    config.addinivalue_line(
        "markers", "slow: mark test as slow-running benchmark (deselect with -m 'not slow')"
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    # Keep recording files (uploads, trims, recorder) out of the real data/recordings
    from app.core.config import settings
    from app.services.shared import recorder as recorder_module

    monkeypatch.setattr(settings, "RECORDINGS_DIR", str(tmp_path / "recordings"))
    monkeypatch.setattr(recorder_module, "_recorder", None)

    from app.db.migrate import ensure_schema
    from app.db.session import init_engine

    engine = init_engine()
    ensure_schema(engine)

    from app.app import app

    with TestClient(app) as test_client:
        yield test_client
