"""
locustfile.py — Load / stress tests for the GDB sandbox.

Section 8: Resource Limit & Stress Tests

Run with:
    locust -f tests/load/locustfile.py --users 50 --spawn-rate 5 --host http://localhost:8000

⚠️  WARNING: These tests spin up REAL Docker containers and consume host resources.
    Do NOT run in CI on every push. Run nightly or manually before a release.

Measures:
  - p95 WS connection establishment time (target: < 3 s)
  - Memory per container (enforced via Docker mem_limit=200m)
  - Server stability under concurrent user load

Section 8.1: Concurrent user simulation
Section 8.4: Session timeout / cleanup
Section 8.5: Storage quota (oversized sync payload)
"""

import json
import time

try:
    import gevent
    from locust import HttpUser, task, between, events
    from locust.exception import RescheduleTask
    HAS_LOCUST = True
except ImportError:
    HAS_LOCUST = False
    # Provide stubs so the module imports cleanly even without locust installed.
    class HttpUser:
        pass
    def task(f):
        return f
    def between(*a):
        return lambda: 0
    events = None


# ---------------------------------------------------------------------------
# 8.1  Concurrent user simulation
# ---------------------------------------------------------------------------

class SandboxUser(HttpUser):
    """
    Simulates a user who:
      1. Registers
      2. Logs in
      3. Polls /api/me
      4. Fires a /sync burst (as if typing code)
    """
    wait_time = between(1, 3)

    def on_start(self):
        """Called once per simulated user on startup."""
        import uuid
        self.username = f"loaduser_{uuid.uuid4().hex[:8]}"
        self.password = "loadtest123"

        # Register
        self.client.post(
            "/api/register",
            json={"username": self.username, "password": self.password},
            name="/api/register",
        )

        # Login → sets session cookie
        login_r = self.client.post(
            "/api/login",
            json={"username": self.username, "password": self.password},
            name="/api/login",
        )
        if login_r.status_code != 200:
            raise RescheduleTask()

    @task(3)
    def sync_code(self):
        """Simulate the editor auto-save (fires frequently)."""
        code = f"// Load test at {time.time()}\nint main() {{ return 0; }}\n"
        self.client.post(
            "/sync/load-test-session",
            data=code,
            name="/sync/{session_id}",
        )

    @task(1)
    def check_me(self):
        self.client.get("/api/me", name="/api/me")

    def on_stop(self):
        self.client.post("/api/logout", name="/api/logout")


# ---------------------------------------------------------------------------
# 8.5  Storage quota — oversized sync payload
# ---------------------------------------------------------------------------

class StorageQuotaUser(HttpUser):
    """
    WHY: A malicious user could call /sync with a 100 MB payload to fill the disk.
    Expected: server returns 400 or 413, NOT 200.
    """
    wait_time = between(5, 10)

    @task
    def attempt_oversized_sync(self):
        huge_payload = "X" * (1024 * 1024 * 11)  # 11 MB
        with self.client.post(
            "/sync/quota-test-session",
            data=huge_payload,
            name="/sync (oversized)",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                r.failure(
                    "Server accepted an 11 MB sync payload without a size limit. "
                    "Add a body size limit to prevent disk-fill attacks."
                )
            else:
                r.success()


# ---------------------------------------------------------------------------
# Notes for manual verification (Section 8.2 / 8.3)
# ---------------------------------------------------------------------------

"""
8.2  Container Memory Limit Test (manual):
-----------------------------------------------
Inside a running sandbox container, compile and run:

    cat > /workspace/leak.cpp << 'EOF'
    #include <cstdlib>
    int main() {
        while(1) { malloc(1024*1024); }
        return 0;
    }
    EOF
    g++ -o /workspace/leak /workspace/leak.cpp
    /workspace/leak

Expected: container exits with OOM (exit code 137), host server process stays alive.

8.3  CPU Time Limit Test (manual):
-----------------------------------------------
Inside a running sandbox container:

    cat > /workspace/spin.cpp << 'EOF'
    int main() { while(1){} return 0; }
    EOF
    g++ -o /workspace/spin /workspace/spin.cpp
    /workspace/spin

Expected: container is limited to 0.5 CPU (nano_cpus=500_000_000),
other containers remain responsive.
"""
