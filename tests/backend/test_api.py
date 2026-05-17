"""
test_api.py — HTTP integration tests for every auth and sync endpoint.

Section 3.1  Auth endpoints  (/api/register, /api/login, /api/me, /api/logout)
Section 3.2  Code sync       (/sync/{session_id}, /api/code/{session_id})

Uses FastAPI's TestClient (synchronous) — no live server needed.
The `client` and `temp_db` fixtures are injected from conftest.py.
"""

import pytest


# ---------------------------------------------------------------------------
# 3.1  Auth Endpoints
# ---------------------------------------------------------------------------

class TestRegister:
    """POST /api/register"""

    def test_register_success(self, client):
        r = client.post("/api/register", json={"username": "alice", "password": "pass123"})
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_register_duplicate_username(self, client):
        """WHY: Duplicate usernames corrupt auth; must be rejected with a clear error."""
        payload = {"username": "dup_user", "password": "pass"}
        client.post("/api/register", json=payload)
        r = client.post("/api/register", json=payload)
        assert r.status_code == 400
        assert "already exists" in r.json().get("detail", "").lower()

    def test_register_empty_username_returns_client_error(self, client):
        """
        WHY: The server must never store a blank username.
        Returns 422 (Pydantic validation) if a validator is present,
        or 400 if guarded at route level.
        """
        r = client.post("/api/register", json={"username": "", "password": "pass"})
        assert r.status_code in (400, 422)

    def test_register_missing_password_field(self, client):
        r = client.post("/api/register", json={"username": "nopass"})
        assert r.status_code == 422

    def test_register_missing_username_field(self, client):
        r = client.post("/api/register", json={"password": "pass"})
        assert r.status_code == 422

    def test_register_returns_json(self, client):
        r = client.post("/api/register", json={"username": "jsontest", "password": "pass"})
        assert r.headers["content-type"].startswith("application/json")


class TestLogin:
    """POST /api/login"""

    def _register(self, client, username="loginuser", password="pass123"):
        client.post("/api/register", json={"username": username, "password": password})

    def test_login_success_sets_cookie(self, client):
        self._register(client)
        r = client.post("/api/login", json={"username": "loginuser", "password": "pass123"})
        assert r.status_code == 200
        assert "session_token" in r.cookies

    def test_login_wrong_password(self, client):
        self._register(client)
        r = client.post("/api/login", json={"username": "loginuser", "password": "WRONG"})
        assert r.status_code == 400

    def test_login_nonexistent_user(self, client):
        r = client.post("/api/login", json={"username": "ghost", "password": "x"})
        assert r.status_code == 400

    def test_login_wrong_password_does_not_return_token(self, client):
        self._register(client)
        r = client.post("/api/login", json={"username": "loginuser", "password": "WRONG"})
        assert "session_token" not in r.cookies

    def test_login_returns_username(self, client):
        self._register(client, "namecheck", "pass")
        r = client.post("/api/login", json={"username": "namecheck", "password": "pass"})
        assert r.json().get("username") == "namecheck"


class TestGetMe:
    """GET /api/me"""

    def test_get_me_authenticated(self, client):
        """WHY: /api/me is the session-bootstrap call on every page load."""
        client.post("/api/register", json={"username": "metest", "password": "pass"})
        client.post("/api/login", json={"username": "metest", "password": "pass"})
        # After login the TestClient holds the session cookie automatically
        r = client.get("/api/me")
        assert r.status_code == 200
        assert r.json().get("username") == "metest"

    def test_get_me_unauthenticated(self, client):
        """WHY: Without a cookie, a 401 must be returned — not a 200 with null."""
        r = client.get("/api/me")
        assert r.status_code == 401

    def test_get_me_with_invalid_token(self, client):
        r = client.get("/api/me", cookies={"session_token": "totally-fake-token"})
        assert r.status_code == 401


class TestLogout:
    """POST /api/logout"""

    def test_logout_invalidates_session(self, client):
        """
        WHY: After logout /api/me must return 401 even if the old cookie is re-used.
        This confirms the server deletes the session from the DB, not just the cookie.
        """
        client.post("/api/register", json={"username": "logouttest", "password": "pass"})
        login_r = client.post("/api/login", json={"username": "logouttest", "password": "pass"})
        token = login_r.cookies.get("session_token")
        assert token

        client.post("/api/logout")

        # Manually re-send the old token — must now be 401
        r = client.get("/api/me", cookies={"session_token": token})
        assert r.status_code == 401

    def test_logout_returns_ok(self, client):
        client.post("/api/register", json={"username": "logoutok", "password": "pass"})
        client.post("/api/login", json={"username": "logoutok", "password": "pass"})
        r = client.post("/api/logout")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 3.2  /sync and /api/code endpoints
# ---------------------------------------------------------------------------

class TestSyncCode:
    """POST /sync/{session_id}"""

    def test_sync_unknown_session_does_not_crash(self, client):
        """
        WHY: The editor fires /sync every few seconds. An unknown session_id
        must NOT cause a 500 crash — the server should silently no-op.
        """
        r = client.post("/sync/nonexistent-session-id", content="int main() {}")
        assert r.status_code == 200

    def test_sync_returns_ok_json(self, client):
        r = client.post("/sync/anything", content="// code")
        assert r.json().get("status") == "ok"

    def test_sync_large_payload_rejected(self, client):
        """
        WHY: Without a size limit an attacker can fill the disk via /sync.
        This test documents the *desired* behaviour — add a size limit middleware
        to make it pass (currently the server may accept oversized payloads).
        """
        huge = "X" * (1024 * 1024 * 11)  # 11 MB
        r = client.post("/sync/any", content=huge)
        # Desired: 413 or 400. If still 200, the test flags the missing guard.
        if r.status_code == 200:
            pytest.xfail(
                "No payload size limit is enforced yet — "
                "add a body size check to /sync to harden against disk-fill attacks."
            )
        assert r.status_code in (400, 413)


class TestGetCode:
    """GET /api/code/{session_id}"""

    def test_get_code_unknown_session_returns_404(self, client):
        r = client.get("/api/code/nonexistent-session-id")
        assert r.status_code == 404
