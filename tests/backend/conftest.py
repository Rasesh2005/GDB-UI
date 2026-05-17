"""
conftest.py — Shared pytest fixtures for backend tests.

Provides:
  - A temp SQLite DB patched into the app before each test
  - A FastAPI TestClient pre-configured with that DB
  - Helper to create & login a user in a single call
"""

import os
import sqlite3
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Patch DB_PATH BEFORE importing the app so init_db() targets the temp file.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="function")
def temp_db(tmp_path, monkeypatch):
    """
    Creates a fresh temporary SQLite database for every test function.
    Patches script.DB_PATH so every import of DB_PATH resolves to the temp file.
    """
    db_file = str(tmp_path / "test.db")

    # Patch both the module-level variable AND the os.makedirs guard
    monkeypatch.setenv("GDB_TEST_DB", db_file)

    import script
    monkeypatch.setattr(script, "DB_PATH", db_file)
    monkeypatch.setattr(script, "DATA_USERS_DIR", str(tmp_path / "users"))
    monkeypatch.setattr(script, "SANDBOXES_DIR", str(tmp_path / "sandboxes"))

    os.makedirs(str(tmp_path / "users"), exist_ok=True)
    os.makedirs(str(tmp_path / "sandboxes"), exist_ok=True)

    # Re-run DB initialisation against the temp file
    script.init_db()

    yield db_file


@pytest.fixture(scope="function")
def client(temp_db):
    """
    Returns a FastAPI TestClient for every test.
    The TestClient shares the same in-process app, so the patched DB_PATH applies.
    """
    import script
    with TestClient(script.app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def registered_user(client):
    """Registers a user and returns (username, password)."""
    username, password = "testuser", "testpass123"
    resp = client.post("/api/register", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Register failed: {resp.text}"
    return username, password


@pytest.fixture
def logged_in_client(client, registered_user):
    """Returns a (client, username) tuple where the client holds a valid session cookie."""
    username, password = registered_user
    resp = client.post("/api/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return client, username
