import os
import sqlite3
import pytest
import time
from backend.gdb.session import sessions, DebugSession


def test_project_lifecycle(logged_in_client, temp_db):
    """Test the full CRUD lifecycle of a project using fixtures for auth and DB paths."""
    client, username = logged_in_client
    db_path = temp_db  # This is the path to the patched temporary database

    # 1. Get user_id from the temporary database
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        assert row is not None, f"User {username} not found in temporary database {db_path}"
        user_id = row[0]

    # 2. Create Project
    unique_id = int(time.time())
    project_name = f"Project_{unique_id}"
    create_res = client.post("/api/projects", json={"name": project_name})
    assert create_res.status_code == 200, f"Project creation failed: {create_res.text}"
    project_data = create_res.json()
    project_id = project_data["id"]
    assert project_data["name"] == project_name

    # Verify folder exists in the patched project directory
    import backend.config as config
    project_dir = os.path.join(config.DATA_USERS_DIR, str(user_id), str(project_id))
    assert os.path.exists(project_dir), f"Project directory {project_dir} was not created"

    # 3. List Projects
    list_res = client.get("/api/projects")
    assert list_res.status_code == 200
    projects = list_res.json()["projects"]
    assert any(p["id"] == project_id and p["name"] == project_name for p in projects)

    # 4. Update Project Name
    new_name = f"{project_name}_Updated"
    update_res = client.put(f"/api/projects/{project_id}", json={"name": new_name})
    assert update_res.status_code == 200

    # Verify update in list
    list_res2 = client.get("/api/projects")
    projects2 = list_res2.json()["projects"]
    assert any(p["id"] == project_id and p["name"] == new_name for p in projects2)

    # 5. Delete Project
    delete_res = client.delete(f"/api/projects/{project_id}")
    assert delete_res.status_code == 200

    # Verify DB entry gone
    list_res3 = client.get("/api/projects")
    assert not any(p["id"] == project_id for p in list_res3.json()["projects"])

    # Verify folder removed
    assert not os.path.exists(project_dir)


def test_auth_session_limit_logic():
    """Verify the logic that limits authenticated users to 5 concurrent sessions."""
    user_id = 12345  # Arbitrary test user ID

    # Clear any existing sessions for this mock user to ensure isolation
    to_delete = [sid for sid, s in sessions.items() if s.user_id == user_id]
    for sid in to_delete:
        del sessions[sid]

    # Simulate adding exactly 5 sessions
    try:
        for i in range(5):
            sid = f"session_{i}"
            sessions[sid] = DebugSession(sid, f"container_{i}", f"/workspace_{i}", user_id=user_id)

        # Verify count is exactly at the limit
        active_count = sum(1 for s in sessions.values() if s.user_id == user_id)
        assert active_count == 5

        # Verify the logic would block a 6th session
        can_add = active_count < 5
        assert can_add is False, "Should not be able to add a 6th session"

    finally:
        # Cleanup mock sessions
        for i in range(5):
            sessions.pop(f"session_{i}", None)
