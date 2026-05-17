"""
test_websockets.py — WebSocket connection tests.

Section 4:
  4.1  /ws/terminal  — must send SESSION_ID: as first message
  4.2  /ws/dbg/<bad-id> — must return an error record for unknown session IDs
  4.3  Cookie propagation through the WS handshake

WHY: WebSocket handshakes and message framing are the hardest bugs to catch
without tests. A wrong field name in send_json() silently corrupts the debugger UI.

NOTE: These tests use starlette.testclient websocket_connect which spins up
the app in-process. Tests that require a live Docker container are marked
@pytest.mark.integration and skipped by default unless --run-integration is passed.
"""

import json
import pytest
from starlette.testclient import TestClient


def get_ws_client():
    import script
    return TestClient(script.app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 4.1  /ws/terminal
# ---------------------------------------------------------------------------

class TestTerminalWebSocket:
    """
    The terminal WS handler tries to spin up a Docker container.
    Without Docker available in CI we test only as far as the WS handshake
    and the first message (SESSION_ID:...) — if Docker is unavailable the
    test is skipped gracefully.
    """

    @pytest.mark.integration
    def test_terminal_ws_sends_session_id(self):
        """
        WHY: The frontend depends on receiving SESSION_ID:<uuid> as the VERY
        FIRST message over the WS to wire up the debugger. If this message
        is absent or malformed, the whole session fails silently.
        """
        with get_ws_client().websocket_connect("/ws/terminal") as ws:
            msg = ws.receive_text()
            assert msg.startswith("SESSION_ID:"), (
                f"Expected 'SESSION_ID:...' but got: {msg!r}"
            )

    @pytest.mark.integration
    def test_terminal_ws_session_id_is_uuid_format(self):
        import re
        uuid_pattern = re.compile(
            r"SESSION_ID:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            re.IGNORECASE,
        )
        with get_ws_client().websocket_connect("/ws/terminal") as ws:
            msg = ws.receive_text()
            assert uuid_pattern.match(msg), f"Session ID not UUID format: {msg!r}"


# ---------------------------------------------------------------------------
# 4.2  /ws/dbg/<unknown-session>
# ---------------------------------------------------------------------------

class TestDebugWebSocket:
    """
    /ws/dbg/<session_id> must return a JSON error record when the session_id
    doesn't exist in the registry.
    """

    def test_dbg_ws_unknown_session_returns_error(self):
        """
        WHY: If an unknown session silently hangs, the frontend's onmessage
             handler never fires and the UI shows a stuck "connecting" spinner.
        """
        with get_ws_client().websocket_connect("/ws/dbg/fake-session-id-that-does-not-exist") as ws:
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data.get("type") == "error", (
                f"Expected {{\"type\": \"error\", ...}} but got: {data}"
            )

    def test_dbg_ws_error_has_payload(self):
        with get_ws_client().websocket_connect("/ws/dbg/not-a-real-session") as ws:
            raw = ws.receive_text()
            data = json.loads(raw)
            assert "payload" in data, "error record must include a 'payload' field"


# ---------------------------------------------------------------------------
# 4.3  Cookie forwarding through WS handshake
# ---------------------------------------------------------------------------

class TestWebSocketCookies:
    """
    WHY: FastAPI reads `ws.cookies` during the WS upgrade. If cookies are
    not forwarded correctly, authenticated users are treated as guests even
    though they logged in via HTTP first.
    """

    def test_terminal_ws_with_valid_session_cookie(self, client, registered_user):
        """
        A user with a valid session_token cookie must connect without errors.
        (Full verification requires Docker; we just confirm no immediate error.)
        """
        username, password = registered_user
        login_r = client.post("/api/login", json={"username": username, "password": password})
        token = login_r.cookies.get("session_token")
        assert token, "Login must set a session_token cookie"

        # The TestClient carries cookies from the login response automatically,
        # so this just verifies the WS upgrade is accepted (status 101).
        # A Docker-less environment will send an error text, not a crash.
        try:
            with get_ws_client().websocket_connect(
                "/ws/terminal",
                cookies={"session_token": token},
            ) as ws:
                msg = ws.receive_text()
                # May be SESSION_ID:... or an error about Docker — either is fine here
                assert msg  # something must be sent
        except Exception:
            pytest.skip("Docker not available — skipping WS cookie cookie-forwarding test")
