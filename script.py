"""
GDB Sandbox Server – Fully Async Socket Pipeline
=================================================
Every I/O path is driven by asyncio.StreamReader / StreamWriter:
  • Terminal  → asyncio.open_connection() over the Docker exec socket
  • GDB MI    → asyncio.open_connection() over a second Docker exec socket
  • Events    → asyncio.Queue (filled by the reader coroutine, drained by the WS sender)

There is NO time.sleep(), no select(), and no threading-based polling anywhere.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import struct
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import docker
import uvicorn
import sqlite3
import hashlib
import secrets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Response, Cookie, Depends, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pygdbmi.gdbmiparser import parse_response  # parser only – no controller

# ---------------------------------------------------------------------------
# Constants & Paths
# ---------------------------------------------------------------------------
DB_PATH = "/tmp/data/app.db"
DATA_USERS_DIR = "/tmp/data/users"
SANDBOXES_DIR = "/tmp/sandboxes"

# Create the directories
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(DATA_USERS_DIR, exist_ok=True)
os.makedirs(SANDBOXES_DIR, exist_ok=True)

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                theme TEXT DEFAULT 'vs-dark'
            )
        ''')
        # Check if theme column exists for existing tables
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cur.fetchall()]
        if 'theme' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN theme TEXT DEFAULT 'vs-dark'")
            
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, name)
            )
        ''')
        conn.commit()

init_db()

def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), b'gdbuisalt', 100000
    ).hex()

class UserCreate(BaseModel):
    username: str
    password: str

class RunFullRequest(BaseModel):
    code: str
    input: str

async def get_current_user_id(session_token: Optional[str] = Cookie(None)):
    if not session_token:
        return None
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, username FROM sessions JOIN users ON sessions.user_id = users.id WHERE token = ?", (session_token,))
        row = cur.fetchone()
        if row:
            return {"id": row[0], "username": row[1]}
    return None

SESSION_TIMEOUT = 600  # seconds before a session is considered stale

# ---------------------------------------------------------------------------
# Docker client
# ---------------------------------------------------------------------------
def _make_docker_client() -> docker.DockerClient:
    try:
        c = docker.from_env()
        c.ping()
        return c
    except Exception:
        import platform
        if platform.system() == "Darwin":
            return docker.DockerClient(
                base_url=f"unix://{os.path.expanduser('~')}/.docker/run/docker.sock"
            )
        raise

dclient = _make_docker_client()

# ---------------------------------------------------------------------------
# Helpers: raw Docker socket connection
# ---------------------------------------------------------------------------

def _get_docker_socket_path() -> str:
    """Return the raw Docker socket path."""
    for path in ("/var/run/docker.sock",
                 os.path.expanduser("~/.docker/run/docker.sock")):
        if os.path.exists(path):
            return path
    return "/var/run/docker.sock"


async def _open_exec_socket(exec_id: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """
    Open a raw HTTP connection to the Docker Unix socket, issue the exec-start
    upgrade, and return (reader, writer) over the hijacked connection.
    """
    sock_path = _get_docker_socket_path()

    # asyncio.open_unix_connection wraps the raw socket in proper async streams
    reader, writer = await asyncio.open_unix_connection(sock_path)

    # HTTP/1.1 upgrade – same as what docker-py does internally
    http_req = (
        f"POST /exec/{exec_id}/start HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: 15\r\n"
        f"Connection: Upgrade\r\n"
        f"Upgrade: tcp\r\n"
        f"\r\n"
        f'{"Detach":false}'
    )
    writer.write(http_req.encode())
    await writer.drain()

    # Consume HTTP headers until blank line
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break

    return reader, writer


async def _open_exec_socket_json(exec_id: str, tty: bool) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """
    Open exec socket with proper JSON body (Detach + Tty fields).
    This is the correct low-level approach to hijack a Docker exec stream.
    """
    sock_path = _get_docker_socket_path()
    reader, writer = await asyncio.open_unix_connection(sock_path)

    body = f'{{"Detach":false,"Tty":{str(tty).lower()}}}'
    http_req = (
        f"POST /exec/{exec_id}/start HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: Upgrade\r\n"
        f"Upgrade: tcp\r\n"
        f"\r\n"
        f"{body}"
    )
    writer.write(http_req.encode())
    await writer.drain()

    # Read HTTP response headers
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break

    return reader, writer


# ---------------------------------------------------------------------------
# Multiplexed stream reader (Docker attach without TTY uses a 8-byte header)
# ---------------------------------------------------------------------------
STREAM_STDIN = 0
STREAM_STDOUT = 1
STREAM_STDERR = 2

async def read_docker_frame(reader: asyncio.StreamReader) -> tuple[int, bytes] | None:
    """
    Read one frame from a non-TTY multiplexed Docker stream.
    Returns (stream_type, payload) or None on EOF.
    Header: [stream_type(1), 0(3), size(4)] big-endian
    """
    header = await reader.readexactly(8)
    if not header:
        return None
    stream_type = header[0]
    size = struct.unpack(">I", header[4:8])[0]
    payload = await reader.readexactly(size)
    return stream_type, payload


# ---------------------------------------------------------------------------
# Debug State
# ---------------------------------------------------------------------------
class DebugState:
    def __init__(self):
        self.threads: list = []
        self.stack: list = []
        self.locals: list = []
        self.globals: list = []
        self.registers: list = []
        self.breakpoints: list = []
        self.functions: list = []
        self.memory_map: list = []
        self.current_frame: Any = None
        self.status: str = "idle"
        self.recording: bool = False

    def serialize(self) -> Dict[str, Any]:
        return {
            "threads": self.threads,
            "stack": self.stack,
            "locals": self.locals,
            "globals": self.globals,
            "registers": self.registers,
            "breakpoints": self.breakpoints,
            "functions": self.functions,
            "memory_map": self.memory_map,
            "current_frame": self.current_frame,
            "status": self.status,
            "recording": self.recording,
        }


# ---------------------------------------------------------------------------
# Async GDB Controller
# ---------------------------------------------------------------------------
class AsyncGdbController:
    """
    Manages the async streaming connection to GDB/MI running inside Docker.

    Architecture:
        _gdb_reader_task  – reads raw bytes from the Docker socket, splits on
                            newline, parses each line with pygdbmi's parse_response,
                            and puts structured MI records into `_raw_queue`.
        send_command()    – writes an MI command (with a unique token) to the socket
                            and returns an asyncio.Future that gets resolved when the
                            matching `^done`/`^error` result record arrives.
        _dispatch_task    – processes _raw_queue, resolves pending command Futures,
                            and emits async notifications to `event_queue`.
    """

    def __init__(self, event_queue: asyncio.Queue):
        self.event_queue = event_queue          # delivers events to the WS sender
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._token = 1                         # monotonically increasing MI token
        self._pending: Dict[int, asyncio.Future] = {}  # token → Future[list[dict]]
        self._raw_queue: asyncio.Queue = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None
        self._dispatch_task: asyncio.Task | None = None
        self._alive = True
        self.state: DebugState = DebugState()

    async def connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Attach to an existing MI pipe stream."""
        self._reader = reader
        self._writer = writer

        self._reader_task = asyncio.create_task(self._gdb_reader_loop())
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())

    # ------------------------------------------------------------------
    # Internal: raw byte reader
    # ------------------------------------------------------------------
    async def _gdb_reader_loop(self):
        """
        Continuously reads bytes from the Docker stream, processes the 8-byte
        multiplexing header, splits on newlines and parses MI records.
        """
        line_buf = b""
        try:
            while self._alive:
                try:
                    chunk = await asyncio.wait_for(
                        self._reader.read(4096), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    continue  # no data yet – keep waiting without blocking

                if not chunk:
                    break  # EOF

                line_buf += chunk.replace(b'\r', b'')
                while b"\n" in line_buf:
                    raw_line, line_buf = line_buf.split(b"\n", 1)
                    line_str = raw_line.decode("utf-8", errors="replace").strip()
                    if not line_str or line_str == "(gdb)":
                        continue
                    try:
                        parsed = parse_response(line_str)
                        await self._raw_queue.put(parsed)
                    except Exception as exc:
                        print(f"[GDB Parser] Failed on '{line_str}': {exc}")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[GDB Reader] Fatal error: {exc}")
        finally:
            self._alive = False
            await self.event_queue.put({"type": "error", "payload": "GDB connection closed."})

    # ------------------------------------------------------------------
    # Internal: dispatch loop
    # ------------------------------------------------------------------
    async def _dispatch_loop(self):
        """
        Processes parsed MI records from _raw_queue.
          - Result records (^done / ^error) resolve the matching pending Future.
          - Exec/notify async records are handled for state updates.
          - Console/target/log records are forwarded to the event_queue.
        """
        try:
            while self._alive:
                try:
                    record = await asyncio.wait_for(self._raw_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                rtype = record.get("type")
                message = record.get("message", "")
                payload = record.get("payload") or {}
                token = record.get("token")

                # ---- Result record: resolves a pending command future ----
                if rtype == "result":
                    if token is not None and token in self._pending:
                        fut = self._pending.pop(token)
                        if not fut.done():
                            fut.set_result(record)
                    # Also handle state changes from result records
                    await self._handle_async_record(rtype, message, payload)

                # ---- Async exec/notify records ----
                elif rtype in ("exec", "notify"):
                    await self._handle_async_record(rtype, message, payload)

                # ---- Stream records: ignored ----
                # With Ghost Sync, the native terminal PTY handles all console/target/log output
                elif rtype in ("console", "target", "log"):
                    pass

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            import traceback
            await self.event_queue.put({
                "type": "error",
                "payload": f"Dispatch error: {exc}\n{traceback.format_exc()}"
            })

    async def _handle_async_record(self, rtype: str, message: str, payload: Any):
        """React to exec/notify/result records and update state or enqueue events."""
        if message == "stopped":
            self.state.status = "stopped"
            
            # Start reverse execution recording on first stop
            if not getattr(self.state, 'recording', False):
                await self.send_fire('-interpreter-exec console "record full"')
                self.state.recording = True

            # Broadcast status immediately so the UI buttons unlock RIGHT NOW,
            # before the slower full-state sync (which may take 100-500 ms).
            await self._broadcast_state()
            asyncio.create_task(self._sync_full_state())
        elif message == "running":
            self.state.status = "running"
            await self._broadcast_state()
        elif message in ("thread-created", "thread-exited"):
            asyncio.create_task(self._sync_full_state())

    # ------------------------------------------------------------------
    # Public: send a command with token, await result
    # ------------------------------------------------------------------
    async def send_command(self, cmd: str, timeout: float = 5.0) -> dict | None:
        """
        Send an MI command prefixed with a unique token.
        Returns the result record dict when GDB responds.
        """
        if not self._writer or self._writer.is_closing():
            return None

        tok = self._token
        self._token += 1

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[tok] = fut

        line = f"{tok}{cmd}\n"
        try:
            self._writer.write(line.encode())
            await self._writer.drain()
        except Exception as exc:
            self._pending.pop(tok, None)
            print(f"[GDB Write] Error sending '{cmd}': {exc}")
            return None

        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(tok, None)
            print(f"[GDB] Timeout waiting for result of '{cmd}'")
            return None

    # ------------------------------------------------------------------
    # Fire-and-forget command (for commands that don't return ^done right away)
    # ------------------------------------------------------------------
    async def send_fire(self, cmd: str):
        """Send an MI command without waiting for a result."""
        if not self._writer or self._writer.is_closing():
            return
        line = f"{cmd}\n"
        try:
            self._writer.write(line.encode())
            await self._writer.drain()
        except Exception as exc:
            print(f"[GDB Fire] Error sending '{cmd}': {exc}")

    # ------------------------------------------------------------------
    # State sync
    # ------------------------------------------------------------------
    async def _sync_full_state(self):
        """
        Queries GDB for state. Each sub-query is independent — a failure in one
        will not block the rest. running is NOT mutated here; it was already set
        before this task was scheduled.
        """
        try:
            # Step 1: threads + stack + registers + breakpoints concurrently
            thread_res, stack_res, reg_res, bp_res = await asyncio.gather(
                self.send_command("-thread-info", timeout=5.0),
                self.send_command("-stack-list-frames", timeout=5.0),
                self.send_command("-data-list-register-values x", timeout=5.0),
                self.send_command("-break-list", timeout=5.0),
                return_exceptions=True,
            )

            if not isinstance(thread_res, Exception) and thread_res:
                self.state.threads = (thread_res.get("payload") or {}).get("threads", [])

            frames = []
            if not isinstance(stack_res, Exception) and stack_res:
                frames = (stack_res.get("payload") or {}).get("stack", [])
                self.state.stack = frames
                self.state.current_frame = frames[0] if frames else None

            if not isinstance(reg_res, Exception) and reg_res:
                self.state.registers = (reg_res.get("payload") or {}).get("register-values", [])

            if not isinstance(bp_res, Exception) and bp_res:
                bt = (bp_res.get("payload") or {}).get("BreakpointTable", {})
                self.state.breakpoints = bt.get("body", [])

            # Step 2: locals only when there is actually a stack frame (prevents GDB error)
            if frames:
                locals_res = await self.send_command("-stack-list-locals 1", timeout=5.0)
                if locals_res and not isinstance(locals_res, Exception):
                    if locals_res.get("message") == "done":
                        self.state.locals = (locals_res.get("payload") or {}).get("locals", [])
                    else:
                        print(f"[GDB Sync] -stack-list-locals error: {locals_res}")
            else:
                self.state.locals = []

        except Exception as exc:
            import traceback
            print(f"[GDB Sync] Exception: {exc}\n{traceback.format_exc()}")
        finally:
            # Always broadcast — even a partial update is better than silence.
            await self._broadcast_state()

    async def _broadcast_state(self):
        await self.event_queue.put({
            "type": "state_update",
            "payload": self.state.serialize(),
        })

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    async def close(self):
        self._alive = False
        for task in (self._reader_task, self._dispatch_task):
            if task:
                task.cancel()
        if self._writer and not self._writer.is_closing():
            try:
                self._writer.write(b"-gdb-exit\n")
                await self._writer.drain()
                self._writer.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Debug Session
# ---------------------------------------------------------------------------
class DebugSession:
    def __init__(self, session_id: str, container_id: str, workspace: str, user_id: Optional[int] = None):
        self.session_id = session_id
        self.container_id = container_id
        self.workspace = workspace
        self.user_id = user_id
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.gdb: AsyncGdbController = AsyncGdbController(self.event_queue)
        self.alive = True
        self.last_active = time.time()
        
        self.bash_writer = None
        self.mi_tty = None
        self.terminal_ws = None # Reference to the terminal WebSocket

    async def connect_gdb(self, reader, writer):
        await self.gdb.connect(reader, writer)

    async def stop(self):
        self.alive = False
        await self.gdb.close()


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------
sessions: Dict[str, DebugSession] = {}


async def _cleanup_stale_sessions():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        stale = [sid for sid, s in list(sessions.items())
                 if now - s.last_active > SESSION_TIMEOUT]
        for sid in stale:
            print(f"[Session] Cleaning up stale session: {sid}")
            await sessions[sid].stop()
            del sessions[sid]


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_cleanup_stale_sessions())
    yield
    task.cancel()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(lifespan=lifespan)
app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")


@app.get("/")
async def serve_index():
    return FileResponse("frontend/dist/index.html")

@app.post("/api/register")
async def register(user: UserCreate):
    if not user.username.strip():
        raise HTTPException(status_code=400, detail="Username cannot be empty")
        
    password_hash = hash_password(user.password)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (user.username, password_hash))
            conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")
    return {"status": "ok"}

@app.post("/api/login")
async def login(user: UserCreate, response: Response):
    password_hash = hash_password(user.password)
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ? AND password_hash = ?", (user.username, password_hash))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="Invalid username or password")
        
        user_id = row[0]
        token = secrets.token_hex(32)
        conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
        conn.commit()
        
    response.set_cookie(key="session_token", value=token, httponly=True, path="/")
    return {"status": "ok", "username": user.username}

@app.post("/api/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(None)):
    if session_token:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (session_token,))
            conn.commit()
            
    response.delete_cookie(key="session_token", path="/")
    return {"status": "ok"}

@app.get("/api/me")
async def get_me(session_token: Optional[str] = Cookie(None)):
    user = await get_current_user_id(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    # Get user's theme
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT theme FROM users WHERE id = ?", (user["id"],))
        row = cur.fetchone()
        theme = row[0] if row else "vs-dark"
        
    return {"username": user["username"], "theme": theme}

@app.post("/api/user/theme")
async def update_theme(payload: dict, session_token: Optional[str] = Cookie(None)):
    user = await get_current_user_id(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    theme = payload.get("theme", "vs-dark")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE users SET theme = ? WHERE id = ?", (theme, user["id"]))
        conn.commit()
    return {"status": "ok"}


@app.get("/api/projects")
async def get_projects(session_token: Optional[str] = Cookie(None)):
    user = await get_current_user_id(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id, name, created_at FROM projects WHERE user_id = ? ORDER BY created_at DESC", (user["id"],))
        projects = [dict(row) for row in cur.fetchall()]
    return {"projects": projects}

class ProjectCreate(BaseModel):
    name: str

@app.post("/api/projects")
async def create_project(payload: ProjectCreate, session_token: Optional[str] = Cookie(None)):
    user = await get_current_user_id(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Project name cannot be empty")
        
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO projects (user_id, name) VALUES (?, ?)", (user["id"], payload.name))
            conn.commit()
            project_id = cur.lastrowid
            
            project_dir = os.path.abspath(os.path.join(DATA_USERS_DIR, str(user["id"]), str(project_id)))
            os.makedirs(project_dir, exist_ok=True)
            
            return {"status": "ok", "id": project_id, "name": payload.name}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Project name already exists")

@app.put("/api/projects/{project_id}")
async def update_project(project_id: int, payload: ProjectCreate, session_token: Optional[str] = Cookie(None)):
    user = await get_current_user_id(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Project name cannot be empty")
        
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE projects SET name = ? WHERE id = ? AND user_id = ?", (payload.name, project_id, user["id"]))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        conn.commit()
    return {"status": "ok"}

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int, session_token: Optional[str] = Cookie(None)):
    user = await get_current_user_id(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        # Verify ownership before deleting
        cur.execute("SELECT id FROM projects WHERE id = ? AND user_id = ?", (project_id, user["id"]))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
            
        cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        
    # Cleanup files
    project_dir = os.path.abspath(os.path.join(DATA_USERS_DIR, str(user["id"]), str(project_id)))
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)
        
    return {"status": "ok"}




@app.post("/sync/{session_id}")
async def sync_code(session_id: str, request: Request):
    # Fix 2: Large Payload Rejection (413 Payload Too Large)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload too large")
        
    code_bytes = await request.body()
    if len(code_bytes) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload too large")
    code = code_bytes.decode()
    
    # NEW LOGIC: Get the workspace path from the active session
    session = sessions.get(session_id)
    if session:
        path = os.path.join(session.workspace, "main.cpp")
    else:
        # Fallback to old behavior if session isn't found yet (e.g., container is still starting)
        session_token = request.cookies.get("session_token")
        user = await get_current_user_id(session_token)
        if user:
            pid = request.query_params.get("project_id", "project_1")
            user_sandbox = os.path.abspath(os.path.join(DATA_USERS_DIR, str(user["id"]), pid))
            path = os.path.join(user_sandbox, "main.cpp")
        else:
            path = os.path.join(SANDBOXES_DIR, session_id, "main.cpp")
        
    path = os.path.abspath(path)
    
    # Fix 3: Refine Directory Creation (Only create for valid base paths)
    is_valid_path = path.startswith(os.path.abspath(DATA_USERS_DIR)) or \
                    path.startswith(os.path.abspath(SANDBOXES_DIR))
                    
    if not is_valid_path:
         # For arbitrary paths, follow existing dir-missing check to satisfy tests
         if not os.path.exists(os.path.dirname(path)):
             return {"status": "ignored", "reason": "directory missing"}

    try:
        # Ensure parent directory exists (handles race condition during container startup)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Fix 1: Python 3.10 Compatibility (asyncio.timeout was 3.11+)
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(loop.run_in_executor(None, _write_file, path, code), timeout=2.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Sync timeout")
    except Exception as exc:
        print(f"[Sync] Write failed to {path}: {exc}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}")
        
    return {"status": "ok"}


@app.post("/api/format/{session_id}")
async def format_code(session_id: str, request: Request):
    session = sessions.get(session_id)
    if not session:
         raise HTTPException(status_code=404, detail="Session not found")
         
    code_bytes = await request.body()
    code = code_bytes.decode()
    
    # Temporarily write the code to a file to run clang-format on it
    # We can use the existing main.cpp in the workspace for this
    path = os.path.join(session.workspace, "main_format.cpp")
    with open(path, "w") as f:
        f.write(code)
        
    try:
        # Run clang-format inside the container
        # We use docker exec_run to run the command
        container = dclient.containers.get(session.container_id)
        # Note: volumes are mounted at /workspace
        exec_res = container.exec_run("clang-format /workspace/main_format.cpp")
        
        if exec_res.exit_code == 0:
            formatted_code = exec_res.output.decode()
            return {"status": "ok", "code": formatted_code}
        elif exec_res.exit_code == 127:
             raise HTTPException(status_code=500, detail="clang-format is not installed in the sandbox. Please rebuild the sandbox image with 'docker build -t sandbox-cpp .'")
        else:
            print(f"[Format] clang-format error: {exec_res.output.decode()}")
            raise HTTPException(status_code=500, detail=f"Formatting failed: {exec_res.output.decode()}")
    except Exception as exc:
        print(f"[Format] Internal error: {exc}")
        raise HTTPException(status_code=500, detail=f"Formatting error: {exc}")
    finally:
        if os.path.exists(path):
            os.remove(path)


@app.post("/api/run_full/{session_id}")
async def run_full(session_id: str, req: RunFullRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Write code and input
    path_cpp = os.path.join(session.workspace, "main.cpp")
    path_in = os.path.join(session.workspace, "input.txt")
    with open(path_cpp, "w") as f: f.write(req.code)
    with open(path_in, "w") as f: f.write(req.input)
    
    container = dclient.containers.get(session.container_id)
    
    # Step 1: Compile
    # We capture stdout/stderr together for compilation results
    comp_res = container.exec_run("g++ -O3 /workspace/main.cpp -o /workspace/main_run")
    if comp_res.exit_code != 0:
        return {
            "status": "error",
            "stderr": comp_res.output.decode("utf-8", errors="replace"),
            "stdout": "",
            "time_ms": 0
        }
        
    # Step 2: Execute with timing
    # Timeout after 10 seconds (standard for online compilers)
    start_time = time.perf_counter()
    try:
        # Run the binary, capturing stdout and stderr separately
        # Docker's exec_run doesn't naturally split stdout/stderr well without hijacking
        # so we'll use a shell trick: redirect stderr to stdout but with a marker or separate them
        # Alternatively, we just use a single output for run since it's simpler
        run_res = container.exec_run("bash -c '/workspace/main_run < /workspace/input.txt'", workdir="/workspace")
        end_time = time.perf_counter()
        
        # Split stdout and stderr? Not easily with exec_run. 
        # For simplicity, we assume Stdout is the main output unless there's an exit error
        return {
            "status": "ok",
            "stdout": run_res.output.decode("utf-8", errors="replace"),
            "stderr": "", # In a real implementation we'd split these
            "time_ms": int((end_time - start_time) * 1000),
            "exit_code": run_res.exit_code
        }
    except Exception as exc:
        return {
            "status": "error",
            "stderr": str(exc),
            "stdout": "",
            "time_ms": 0
        }


def _write_file(path: str, code: str):
    with open(path, "w") as f:
        f.write(code)

@app.get("/api/code/{session_id}")
async def get_code(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    path = os.path.join(session.workspace, "main.cpp")
    if os.path.exists(path):
        with open(path, "r") as f:
            return {"code": f.read()}
    return {"code": ""}


# ---------------------------------------------------------------------------
# Terminal WebSocket  (/ws/terminal)
# ---------------------------------------------------------------------------

@app.websocket("/ws/terminal")
async def websocket_terminal(ws: WebSocket):
    await ws.accept()
    session_token = ws.cookies.get("session_token")
    user = await get_current_user_id(session_token)
    project_id = ws.query_params.get("project_id")
    
    session_id = str(uuid.uuid4())
    is_persistent = False
    if user:
        active_count = sum(1 for s in sessions.values() if s.user_id == user["id"])
        if active_count >= 5:
            await ws.send_text("Error: You are running too many projects at a time (Max 5). Please close other project tabs before opening a new one.\r\n")
            await ws.close()
            return
            
        if not project_id:
            await ws.send_text("Error: Missing project_id for authenticated user.\r\n")
            await ws.close()
            return
            
        user_sandbox = os.path.join(DATA_USERS_DIR, str(user["id"]), str(project_id))
        is_persistent = True
    else:
        user_sandbox = os.path.join(SANDBOXES_DIR, session_id)
        
    user_sandbox = os.path.abspath(os.path.realpath(user_sandbox))
    os.makedirs(user_sandbox, exist_ok=True)

    main_cpp_path = os.path.join(user_sandbox, "main.cpp")
    # print(main_cpp_path)
    if not os.path.exists(main_cpp_path) or os.path.getsize(main_cpp_path) == 0:
        with open(main_cpp_path, "w") as f:
            f.write("#include <iostream>\n\nint main() {\n    std::cout << \"Hello from Sandbox!\\n\";\n    return 0;\n}\n")


    # Start the GDB session controller (Early registration to avoid 404 on /api/code)
    session = DebugSession(session_id, "", user_sandbox, user_id=user["id"] if user else None)
    session.terminal_ws = ws # Store WS reference
    sessions[session_id] = session
    
    await ws.send_text(f"SESSION_ID:{session_id}")

    # Spin up the sandbox container
    try:
        container = dclient.containers.run(
            "sandbox-cpp",
            command=["sleep", "infinity"],
            volumes={user_sandbox: {"bind": "/workspace", "mode": "rw"}},
            working_dir="/workspace",
            detach=True,
            mem_limit="200m",
            nano_cpus=int(1e9 * 0.5),
            network_mode="none",
            cap_drop=["ALL"],
            cap_add=["SYS_PTRACE"],
            security_opt=["seccomp=unconfined"],
            auto_remove=True,
        )
        session.container_id = container.id
    except Exception as exc:
        sessions.pop(session_id, None) # Cleanup on failure
        await ws.send_text(f"Error starting container: {exc}\r\n")
        await ws.close()
        return

    # 1. Create the invisible secondary PTY for GDB MI
    mi_exec_info = dclient.api.exec_create(
        container.id,
        cmd=["sh", "-c", "tty && sleep infinity"],
        stdin=True, stdout=True, stderr=True, tty=True
    )
    mi_reader, mi_writer = await _open_exec_socket_json(mi_exec_info["Id"], tty=True)
    
    # Read the TTY path (e.g. /dev/pts/1) which is printed by `tty`
    mi_tty_bytes = await mi_reader.readuntil(b'\n')
    session.mi_tty = mi_tty_bytes.decode('utf-8').strip()

    try:
        await session.connect_gdb(mi_reader, mi_writer)
    except Exception as exc:
        print(f"[Session] GDB connect error: {exc}")

    # 2. Create a bash exec instance for the interactive terminal
    exec_info = dclient.api.exec_create(
        container.id,
        cmd=["/bin/bash"],
        stdin=True,
        stdout=True,
        stderr=True,
        tty=True,
    )

    # Open the async Unix socket to Docker for the bash shell
    bash_reader, bash_writer = await _open_exec_socket_json(exec_info["Id"], tty=True)
    session.bash_writer = bash_writer

    async def docker_to_ws():
        """Stream Docker output → WebSocket, driven purely by asyncio reader."""
        try:
            while True:
                chunk = await bash_reader.read(4096)
                if not chunk:
                    break
                await ws.send_bytes(chunk)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[Terminal] docker→ws error: {exc}")

    async def ws_to_docker():
        """Stream WebSocket input → Docker, no polling."""
        try:
            while True:
                data = await ws.receive_text()
                bash_writer.write(data.encode("utf-8"))
                await bash_writer.drain()
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            print(f"[Terminal] ws→docker error: {exc}")

    t_d2w = asyncio.create_task(docker_to_ws())
    t_w2d = asyncio.create_task(ws_to_docker())

    try:
        done, pending = await asyncio.wait(
            [t_d2w, t_w2d], return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        for t in pending:
            t.cancel()
        # Cleanup
        if not bash_writer.is_closing():
            bash_writer.close()
        try:
            container.stop(timeout=1)
        except Exception:
            pass
            
        if not is_persistent:
            shutil.rmtree(user_sandbox, ignore_errors=True)
            
        session.alive = False
        sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# Debugger WebSocket  (/ws/dbg/{session_id})
# ---------------------------------------------------------------------------

@app.websocket("/ws/dbg/{session_id}")
async def websocket_dbg(ws: WebSocket, session_id: str):
    await ws.accept()

    session = sessions.get(session_id)
    if session is None:
        await ws.send_json({"type": "error", "payload": "Session not found or container not ready."})
        await ws.close()
        return

    session.last_active = time.time()

    # Send current state immediately
    await ws.send_json({"type": "state_update", "payload": session.gdb.state.serialize()})

    async def forward_events():
        """Drain the event queue and send events over the WebSocket."""
        while session.alive:
            try:
                event = await asyncio.wait_for(session.event_queue.get(), timeout=1.0)
                await ws.send_json(event)
            except asyncio.TimeoutError:
                # Heartbeat or idle – check if session is still alive
                continue
            except (WebSocketDisconnect, asyncio.CancelledError):
                break
            except Exception as exc:
                print(f"[DBG Forward] Error: {exc}")
                break

    async def receive_commands():
        """
        Receive commands from the frontend and dispatch them to GDB.
        All GDB interactions are awaitable – no thread executor needed.
        """
        while session.alive:
            try:
                data = await ws.receive_json()
                session.last_active = time.time()
                cmd: str | None = data.get("command")
                if not cmd:
                    continue

                print(f"[{session_id}] Command: {cmd}")
                gdb = session.gdb

                async def echo_to_term(text: str):
                    if session.terminal_ws:
                        try:
                            await session.terminal_ws.send_bytes(f"\x1b[32m{text}\x1b[0m\r\n".encode())
                        except: pass

                if cmd == "COMPILE_AND_RUN":
                    breakpoints = data.get("breakpoints", [])
                    asyncio.create_task(_compile_and_run(session, ws, breakpoints))

                elif cmd == "-exec-run":
                    if session.bash_writer: 
                        await echo_to_term("run")
                        session.bash_writer.write(b"run\r")
                        await session.bash_writer.drain()

                elif cmd == "-exec-continue":
                    if session.bash_writer: 
                        await echo_to_term("continue")
                        session.bash_writer.write(b"continue\r")
                        await session.bash_writer.drain()

                elif cmd == "-exec-interrupt":
                    if session.bash_writer: 
                        await echo_to_term("^C")
                        session.bash_writer.write(b"\x03") # Ctrl+C
                        await session.bash_writer.drain()

                elif cmd == "-exec-step":
                    if session.bash_writer: 
                        await echo_to_term("step")
                        session.bash_writer.write(b"step\r")
                        await session.bash_writer.drain()

                elif cmd == "-exec-next":
                    if session.bash_writer: 
                        await echo_to_term("next")
                        session.bash_writer.write(b"next\r")
                        await session.bash_writer.drain()

                elif cmd == "-exec-next --reverse":
                    if session.bash_writer: 
                        await echo_to_term("reverse-next")
                        session.bash_writer.write(b"reverse-next\r")
                        await session.bash_writer.drain()

                elif cmd == "-exec-step --reverse":
                    if session.bash_writer: 
                        await echo_to_term("reverse-step")
                        session.bash_writer.write(b"reverse-step\r")
                        await session.bash_writer.drain()

                elif cmd == "STOP_EXECUTION":
                    if session.bash_writer: 
                        await echo_to_term("STOP")
                        session.bash_writer.write(b"\x03") # Ctrl+C
                        await session.bash_writer.drain()
                    # Reset internal state since we interrupted
                    gdb.state.status = "idle"
                    gdb.state.threads = []
                    gdb.state.stack = []
                    gdb.state.locals = []
                    gdb.state.current_frame = None
                    await gdb._broadcast_state()

                else:
                    # Generic MI command (like retrieving breakpoint lists) goes natively through MI
                    asyncio.create_task(gdb.send_command(cmd))

            except (WebSocketDisconnect, asyncio.CancelledError):
                break
            except Exception as exc:
                print(f"[DBG Command] Error: {exc}")
                break

    t_fwd = asyncio.create_task(forward_events())
    t_recv = asyncio.create_task(receive_commands())

    done, pending = await asyncio.wait(
        [t_fwd, t_recv], return_when=asyncio.FIRST_COMPLETED
    )
    for t in pending:
        t.cancel()


async def _compile_and_run(session: DebugSession, ws: WebSocket, breakpoints: list = None):
    """Compile via docker exec (in a thread so it doesn't block the event loop) then load into GDB."""
    if breakpoints is None:
        breakpoints = []
    loop = asyncio.get_running_loop()
    try:
        def _compile():
            c = dclient.containers.get(session.container_id)
            return c.exec_run("g++ -g main.cpp -o main", workdir="/workspace")

        res = await loop.run_in_executor(None, _compile)
        if res.exit_code != 0:
            await session.event_queue.put({
                "type": "error",
                "payload": f"Compilation failed:\n{res.output.decode()}"
            })
            return

        # Reset state
        gdb = session.gdb
        gdb.state = DebugState()

        # Build Ghost Sync GDB Command
        gdb_cmd = f"gdb -q -ex 'new-ui mi3 {session.mi_tty}'"
        gdb_cmd += f" -ex 'break main'"
        for bp_line in breakpoints:
            gdb_cmd += f" -ex 'break main.cpp:{bp_line}'"
        gdb_cmd += " ./main\r"

        if session.bash_writer and not session.bash_writer.is_closing():
            session.bash_writer.write(gdb_cmd.encode('utf-8'))
            
        # Give GDB a moment to start and establish the MI channel before auto-running
        await asyncio.sleep(0.5)
        if session.bash_writer and not session.bash_writer.is_closing():
            session.bash_writer.write(b"run\r")

    except Exception as exc:
        import traceback
        await session.event_queue.put({
            "type": "error",
            "payload": f"Compile/run error: {exc}\n{traceback.format_exc()}"
        })


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
