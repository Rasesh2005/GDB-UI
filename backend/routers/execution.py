import os
import time
import asyncio
from fastapi import APIRouter, Request, HTTPException

from backend.config import DATA_USERS_DIR, SANDBOXES_DIR
from backend.models import CodeExecutionRequest
from backend.gdb.session import sessions
from backend.docker_utils import docker_client
from backend.dependencies import get_current_user_id

router = APIRouter()

def _write_file(path: str, code: str):
    with open(path, "w") as f:
        f.write(code)

@router.post("/sync/{session_id}")
async def sync_code(session_id: str, request: Request):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload too large")
        
    code_bytes = await request.body()
    if len(code_bytes) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload too large")
    code = code_bytes.decode()
    
    session = sessions.get(session_id)
    if session:
        path = os.path.join(session.workspace, "main.cpp")
    else:
        session_token = request.cookies.get("session_token")
        user = await get_current_user_id(session_token)
        if user:
            pid = request.query_params.get("project_id", "project_1")
            user_sandbox = os.path.abspath(os.path.join(DATA_USERS_DIR, str(user["id"]), pid))
            path = os.path.join(user_sandbox, "main.cpp")
        else:
            path = os.path.join(SANDBOXES_DIR, session_id, "main.cpp")
        
    path = os.path.abspath(path)
    
    is_valid_path = path.startswith(os.path.abspath(DATA_USERS_DIR)) or \
                    path.startswith(os.path.abspath(SANDBOXES_DIR))
                    
    if not is_valid_path:
         if not os.path.exists(os.path.dirname(path)):
             return {"status": "ignored", "reason": "directory missing"}

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(loop.run_in_executor(None, _write_file, path, code), timeout=2.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Sync timeout")
    except Exception as exc:
        print(f"[Sync] Write failed to {path}: {exc}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}")
        
    return {"status": "ok"}


@router.post("/api/format/{session_id}")
async def format_code(session_id: str, request: Request):
    session = sessions.get(session_id)
    if not session:
         raise HTTPException(status_code=404, detail="Session not found")
         
    code_bytes = await request.body()
    code = code_bytes.decode()
    
    path = os.path.join(session.workspace, "main_format.cpp")
    with open(path, "w") as f:
        f.write(code)
        
    try:
        container = docker_client.containers.get(session.container_id)
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


@router.post("/api/run_full/{session_id}")
async def run_full(session_id: str, req: CodeExecutionRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    path_cpp = os.path.join(session.workspace, "main.cpp")
    path_in = os.path.join(session.workspace, "input.txt")
    with open(path_cpp, "w") as f: f.write(req.code)
    with open(path_in, "w") as f: f.write(req.input)
    
    container = docker_client.containers.get(session.container_id)
    
    if session.gdb.state.status != "idle":
        if session.bash_writer and not session.bash_writer.is_closing():
            session.bash_writer.write(b"quit\r")
            await session.bash_writer.drain()
        session.gdb.state.status = "idle"
        session.gdb.state.threads = []
        session.gdb.state.stack = []
        session.gdb.state.locals = []
        session.gdb.state.current_frame = None
        await session.gdb._broadcast_state()
        
    # Force kill any lingering GDB in the container
    container.exec_run("pkill -9 gdb")
    
    comp_res = container.exec_run("g++ -O3 /workspace/main.cpp -o /workspace/main_run")
    if comp_res.exit_code != 0:
        return {
            "status": "error",
            "stderr": comp_res.output.decode("utf-8", errors="replace"),
            "stdout": "",
            "time_ms": 0
        }
        
    start_time = time.perf_counter()
    try:
        run_res = container.exec_run("bash -c '/workspace/main_run < /workspace/input.txt'", workdir="/workspace")
        end_time = time.perf_counter()
        
        return {
            "status": "ok",
            "stdout": run_res.output.decode("utf-8", errors="replace"),
            "stderr": "",
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


@router.get("/api/code/{session_id}")
async def get_code(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    path = os.path.join(session.workspace, "main.cpp")
    if os.path.exists(path):
        with open(path, "r") as f:
            return {"code": f.read()}
    return {"code": ""}
