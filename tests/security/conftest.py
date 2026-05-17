"""
conftest.py for security tests.
Imports all shared fixtures from the backend conftest via pytest's plugin system.
"""
# pytest automatically discovers conftest.py at every level.
# We re-export the backend conftest fixtures by adding tests/backend to sys.path,
# or we duplicate the minimal fixture here for security tests to be self-contained.

import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True, scope="function")
def temp_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "sec_test.db")
    import script
    monkeypatch.setattr(script, "DB_PATH", db_file)
    monkeypatch.setattr(script, "DATA_USERS_DIR", str(tmp_path / "users"))
    monkeypatch.setattr(script, "SANDBOXES_DIR", str(tmp_path / "sandboxes"))
    os.makedirs(str(tmp_path / "users"), exist_ok=True)
    os.makedirs(str(tmp_path / "sandboxes"), exist_ok=True)
    script.init_db()
    yield db_file


@pytest.fixture(scope="function")
def client(temp_db):
    import script
    with TestClient(script.app, raise_server_exceptions=False) as c:
        yield c
