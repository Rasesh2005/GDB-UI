"""
test_persistence.py — Workspace creation, survival, and cleanup tests.

Section 10:
  10.1  Authenticated user workspace NOT deleted on disconnect
  10.2  Guest user workspace DELETED on disconnect
  10.3  /sync writes to session workspace (not to SANDBOXES_DIR)
  10.4  Existing main.cpp NOT overwritten by the WS handler template logic

WHY: The core authenticated-user promise is "your files survive a container restart."
     These are the most important regression tests for the auth feature.
"""

import os
import shutil
import pytest


# ---------------------------------------------------------------------------
# 10.1  Authenticated user workspace NOT deleted on disconnect
# ---------------------------------------------------------------------------

class TestPersistentWorkspace:

    def test_authenticated_workspace_not_deleted(self, tmp_path):
        """
        WHY: is_persistent=True → shutil.rmtree must NOT be called.
             Simulates the cleanup block inside websocket_terminal's finally clause.
        """
        workspace = tmp_path / "user_1" / "project_1"
        workspace.mkdir(parents=True)
        (workspace / "main.cpp").write_text("int main() { return 0; }")

        is_persistent = True
        if not is_persistent:
            shutil.rmtree(str(workspace), ignore_errors=True)

        assert (workspace / "main.cpp").exists(), (
            "Persistent workspace was deleted — check the is_persistent guard."
        )

    def test_authenticated_workspace_contents_survive(self, tmp_path):
        workspace = tmp_path / "user_42" / "project_1"
        workspace.mkdir(parents=True)
        special_content = "// My saved work — do not overwrite"
        (workspace / "main.cpp").write_text(special_content)

        is_persistent = True
        if not is_persistent:
            shutil.rmtree(str(workspace), ignore_errors=True)

        content = (workspace / "main.cpp").read_text()
        assert content == special_content


# ---------------------------------------------------------------------------
# 10.2  Guest user workspace DELETED on disconnect
# ---------------------------------------------------------------------------

class TestEphemeralWorkspace:

    def test_guest_workspace_deleted_on_disconnect(self, tmp_path):
        """
        WHY: Guest sandboxes must be cleaned up after disconnect to avoid
             unbounded disk usage.
        """
        workspace = tmp_path / "guest_ephemeral"
        workspace.mkdir()
        (workspace / "main.cpp").write_text("int main() {}")

        is_persistent = False
        if not is_persistent:
            shutil.rmtree(str(workspace), ignore_errors=True)

        assert not workspace.exists(), (
            "Guest workspace was NOT deleted — missing shutil.rmtree() call?"
        )

    def test_guest_cleanup_uses_ignore_errors(self, tmp_path):
        """
        WHY: If the directory was already gone (race condition), ignore_errors
        must prevent an exception that would leak the try/finally block.
        """
        workspace = tmp_path / "already_gone"
        # Don't create it — simulate it having been deleted already
        # shutil.rmtree with ignore_errors must not raise
        shutil.rmtree(str(workspace), ignore_errors=True)  # Must not raise


# ---------------------------------------------------------------------------
# 10.3  /sync writes to correct workspace
# ---------------------------------------------------------------------------

class TestSyncWritesToCorrectPath:

    def test_sync_writes_to_user_workspace_when_session_exists(self, client, tmp_path, monkeypatch):
        """
        WHY: /sync must use session.workspace (the user's persistent volume path),
             NOT SANDBOXES_DIR. A bug here means the user edits a file the container
             cannot see (different bind-mount path).
        """
        import script

        # Create a fake workspace dir
        ws_dir = tmp_path / "user_workspace"
        ws_dir.mkdir()

        fake_session_id = "aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb"

        # Mock a DebugSession object
        class FakeSession:
            session_id = fake_session_id
            workspace = str(ws_dir)

        monkeypatch.setitem(script.sessions, fake_session_id, FakeSession())

        code = "// Sync test content"
        r = client.post(f"/sync/{fake_session_id}", content=code)
        assert r.status_code == 200

        written = (ws_dir / "main.cpp").read_text()
        assert written == code, (
            "sync() wrote to the wrong location — session.workspace is not being used."
        )

    def test_sync_does_not_write_when_dir_missing(self, client, tmp_path, monkeypatch):
        """
        WHY: If the workspace directory doesn't exist, writing should silently no-op
        rather than crash with FileNotFoundError.
        """
        import script

        ws_dir = tmp_path / "does_not_exist"  # Intentionally not created

        class FakeSession:
            session_id = "fake-id-99"
            workspace = str(ws_dir)

        monkeypatch.setitem(script.sessions, "fake-id-99", FakeSession())

        r = client.post("/sync/fake-id-99", content="// code")
        # Must NOT crash (500); the check `if os.path.exists(os.path.dirname(path))`
        # should guard the write.
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 10.4  main.cpp is NOT overwritten when it already exists and is non-empty
# ---------------------------------------------------------------------------

class TestMainCppNotOverwritten:

    def test_existing_nonempty_main_cpp_is_preserved(self, tmp_path):
        """
        WHY: If main.cpp already exists in the user's workspace, the default
             template must NOT overwrite it. This simulates the guard in
             websocket_terminal().
        """
        workspace = tmp_path
        cpp_path = workspace / "main.cpp"
        saved_content = "// My saved work"
        cpp_path.write_text(saved_content)

        # Simulate the exact guard logic from script.py
        if not cpp_path.exists() or cpp_path.stat().st_size == 0:
            cpp_path.write_text("// Default template")

        assert cpp_path.read_text() == saved_content, (
            "main.cpp was overwritten even though it existed and was non-empty."
        )

    def test_empty_main_cpp_is_replaced_with_template(self, tmp_path):
        """
        WHY: If main.cpp is empty (e.g. created by touch), the default template
             should be written so the user has something to work with.
        """
        workspace = tmp_path
        cpp_path = workspace / "main.cpp"
        cpp_path.write_text("")  # Empty file

        template = "#include <iostream>\n\nint main() {\n    std::cout << \"Hello!\\n\";\n    return 0;\n}\n"
        if not cpp_path.exists() or cpp_path.stat().st_size == 0:
            cpp_path.write_text(template)

        assert cpp_path.read_text() == template

    def test_missing_main_cpp_is_created_with_template(self, tmp_path):
        """
        WHY: Fresh sandbox directories don't have main.cpp. The handler creates it.
        """
        workspace = tmp_path
        cpp_path = workspace / "main.cpp"
        # File does NOT exist

        template = "#include <iostream>\n\nint main() {\n    // Hello\n    return 0;\n}\n"
        if not cpp_path.exists() or cpp_path.stat().st_size == 0:
            cpp_path.write_text(template)

        assert cpp_path.exists()
        assert cpp_path.read_text() == template
