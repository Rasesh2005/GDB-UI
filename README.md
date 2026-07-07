# GDB-UI

A web-based GDB debugger interface that runs C/C++ programs inside isolated Docker sandboxes with full reverse-debugging support.

## Architecture

| Layer | Details |
|---|---|
| **Backend** | FastAPI server (`backend/`) — handles sessions, GDB/MI, WebSockets |
| **Frontend** | React + Vite app (`frontend/`) — editor, terminal, debug panels |
| **Sandbox** | Each session runs inside a Docker container (`sandbox-cpp` image) |
| **DooD** | Server shares the host Docker socket to spawn sibling containers |

## Prerequisites

- Python 3.10+
- Docker (with the `sandbox-cpp` image built — see below)
- Node.js 18+ (for building the frontend)

## Quick Start (Local Dev)

### 1. Build the sandbox image

```bash
docker build -f Dockerfile -t sandbox-cpp .
```

### 2. Install Python dependencies

```bash
pip install fastapi "uvicorn[standard]" websockets docker pygdbmi
```

### 3. Build the frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

### 4. Run the backend

```bash
python3 -m backend.main
```

The app will be available at **http://localhost:8000**.

## Running with Docker Compose (Production)

> **Note:** Update `docker-compose.yml` to mount the `backend/` directory instead of `script.py` when the Docker image is updated.

```bash
# Build the server image first
docker build -f Dockerfile.server -t gdb-sandbox-server .

# Start everything
docker compose up
```

Access at **http://localhost:8000**.

## Development

### Backend only (hot-reload)

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend dev server (with proxy to backend)

```bash
cd frontend
npm run dev
```

### Run tests

```bash
# Backend tests
pytest tests/

# Frontend tests
npm test
```

## Directory Structure

```
GDB-UI/
├── backend/              # FastAPI application (main entry point)
│   ├── main.py           # App factory, lifespan, router registration
│   ├── config.py         # Paths, timeouts, env config
│   ├── database.py       # SQLite user/session management
│   ├── docker_utils.py   # Docker client helpers
│   ├── models.py         # Pydantic models & DebugState
│   ├── dependencies.py   # Auth dependency injection
│   └── routers/
│       ├── auth.py       # Login, register, logout
│       ├── projects.py   # Project CRUD
│       ├── execution.py  # Run endpoints
│       └── websockets.py # Terminal & GDB debug WebSockets
│   └── gdb/
│       ├── controller.py # AsyncGdbController (GDB/MI protocol)
│       └── session.py    # DebugSession, session registry
├── frontend/             # React + Vite UI
│   └── src/
│       ├── components/   # ControlPanel, DataPanels, Editor, Terminal…
│       └── contexts/     # DebugContext, TerminalContext, AuthContext
├── tests/                # pytest test suite
├── Dockerfile            # sandbox-cpp image (g++, gdb)
├── Dockerfile.server     # Server image
├── docker-compose.yml    # Production orchestration
└── entrypoint.sh         # Docker socket permission fix + uvicorn
```
## TODO / Future Improvements

- **Better GDB Confirmation Handling**: Currently, GDB starts with `-ex 'set confirm off'` to automatically suppress interactive prompts (like deleting breakpoints or terminating threads). In the future, parse GDB's interactive queries programmatically and expose confirmation prompts to the user in the UI instead of using a blanket `set confirm off`.
