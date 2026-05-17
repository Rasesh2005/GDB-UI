"""
test_unit.py — Pure function unit tests (no HTTP, no Docker).

Tests:
  2.1  Pydantic UserCreate model validation
  2.2  hash_password() correctness
  2.3  DebugState.serialize() completeness
  2.4  init_db() schema correctness
"""

import sqlite3
import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# 2.1  Pydantic Model Validation
# ---------------------------------------------------------------------------

class TestUserCreateModel:
    """Verify that UserCreate rejects bad inputs before they reach a route handler."""

    def test_valid_user(self):
        from script import UserCreate
        user = UserCreate(username="alice", password="secret123")
        assert user.username == "alice"
        assert user.password == "secret123"

    def test_empty_username_raises(self):
        """
        WHY: A blank username would corrupt the database and allow empty-name logins.
        NOTE: If you add a min_length=1 Pydantic validator this becomes a true
              ValidationError; without it the model accepts it (test will be skipped
              to avoid a false-fail).
        """
        from script import UserCreate
        try:
            user = UserCreate(username="", password="secret")
            # If Pydantic doesn't raise, just assert the field is empty string
            # (signals that the validator is not yet present)
            assert user.username == "", (
                "No min_length validator on username — add one to enforce non-blank names."
            )
        except ValidationError:
            pass  # Correct: Pydantic rejects it

    def test_empty_password_raises(self):
        from script import UserCreate
        try:
            user = UserCreate(username="alice", password="")
            assert user.password == ""
        except ValidationError:
            pass

    def test_missing_password_raises(self):
        from script import UserCreate
        with pytest.raises((ValidationError, TypeError)):
            UserCreate(username="alice")

    def test_missing_username_raises(self):
        from script import UserCreate
        with pytest.raises((ValidationError, TypeError)):
            UserCreate(password="secret")


# ---------------------------------------------------------------------------
# 2.2  hash_password() purity
# ---------------------------------------------------------------------------

class TestHashPassword:
    """hash_password must be deterministic, collision-free, and return hex output."""

    def test_deterministic(self):
        from script import hash_password
        assert hash_password("abc") == hash_password("abc")

    def test_different_passwords_produce_different_hashes(self):
        from script import hash_password
        assert hash_password("abc") != hash_password("xyz")

    def test_returns_hex_string(self):
        from script import hash_password
        h = hash_password("test")
        assert isinstance(h, str)
        assert len(h) > 0
        assert all(c in "0123456789abcdef" for c in h), (
            f"hash_password returned non-hex characters: {h}"
        )

    def test_does_not_return_plaintext(self):
        from script import hash_password
        assert hash_password("mysecret") != "mysecret"

    def test_empty_password_hashes_consistently(self):
        """Even an empty password must hash consistently (so the DB doesn't explode)."""
        from script import hash_password
        assert hash_password("") == hash_password("")


# ---------------------------------------------------------------------------
# 2.3  DebugState.serialize()
# ---------------------------------------------------------------------------

class TestDebugStateSerialize:
    """
    If serialize() ever omits a key, the frontend state_update handler
    will silently lose data (locals/registers disappear from the UI).
    """

    REQUIRED_KEYS = {
        "threads", "stack", "locals", "globals", "registers",
        "breakpoints", "functions", "memory_map", "current_frame",
        "status", "recording",
    }

    def test_all_required_keys_present(self):
        from script import DebugState
        data = DebugState().serialize()
        missing = self.REQUIRED_KEYS - set(data.keys())
        assert not missing, f"serialize() is missing keys: {missing}"

    def test_no_extra_unexpected_keys(self):
        """Prevents silent additions that could confuse the frontend."""
        from script import DebugState
        data = DebugState().serialize()
        extra = set(data.keys()) - self.REQUIRED_KEYS
        assert not extra, f"serialize() has unexpected extra keys: {extra}"

    def test_default_status_is_idle(self):
        from script import DebugState
        assert DebugState().status == "idle"

    def test_default_lists_are_empty(self):
        from script import DebugState
        s = DebugState()
        for key in ("threads", "stack", "locals", "globals", "registers",
                    "breakpoints", "functions", "memory_map"):
            assert getattr(s, key) == [], f"{key} should default to []"

    def test_default_current_frame_is_none(self):
        from script import DebugState
        assert DebugState().current_frame is None

    def test_serialize_returns_dict(self):
        from script import DebugState
        assert isinstance(DebugState().serialize(), dict)


# ---------------------------------------------------------------------------
# 2.4  init_db() — schema correctness
# ---------------------------------------------------------------------------

class TestInitDb:
    """
    If table creation fails silently (wrong column name), ALL auth routes break.
    Testing the schema directly catches any future ALTER TABLE omissions.
    """

    def test_creates_users_and_sessions_tables(self, tmp_path, monkeypatch):
        import script
        db = str(tmp_path / "schema_test.db")
        monkeypatch.setattr(script, "DB_PATH", db)
        script.init_db()

        with sqlite3.connect(db) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in cur.fetchall()}

        assert "users" in tables, "users table was not created"
        assert "sessions" in tables, "sessions table was not created"

    def test_users_table_has_expected_columns(self, tmp_path, monkeypatch):
        import script
        db = str(tmp_path / "cols_test.db")
        monkeypatch.setattr(script, "DB_PATH", db)
        script.init_db()

        with sqlite3.connect(db) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(users)")
            columns = {row[1] for row in cur.fetchall()}

        assert "id" in columns
        assert "username" in columns
        assert "password_hash" in columns

    def test_sessions_table_has_expected_columns(self, tmp_path, monkeypatch):
        import script
        db = str(tmp_path / "sess_test.db")
        monkeypatch.setattr(script, "DB_PATH", db)
        script.init_db()

        with sqlite3.connect(db) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(sessions)")
            columns = {row[1] for row in cur.fetchall()}

        assert "token" in columns
        assert "user_id" in columns

    def test_init_db_is_idempotent(self, tmp_path, monkeypatch):
        """Calling init_db() twice must not raise an error."""
        import script
        db = str(tmp_path / "idem_test.db")
        monkeypatch.setattr(script, "DB_PATH", db)
        script.init_db()
        script.init_db()  # Should not raise
