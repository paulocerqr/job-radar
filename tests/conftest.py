import os

import pytest

from job_radar.config import get_settings
from job_radar.db import get_engine

URL_PADRAO = "postgresql+psycopg://teste:teste@localhost:5432/teste"


@pytest.fixture(autouse=True)
def ambiente(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", URL_PADRAO))
    monkeypatch.setenv("WORKER_HEARTBEAT_PATH", str(tmp_path / "heartbeat"))
    get_settings.cache_clear()
    get_engine.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
