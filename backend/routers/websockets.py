import os
import time
import uuid
import shutil
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.config import DATA_USERS_DIR, SANDBOXES_DIR
from backend.docker_utils import docker_client, open_exec_socket
from backend.gdb.session import DebugSession, sessions
from backend.dependencies import get_current_user_id
from backend.models import DebugState

router = APIRouter()

@router.websocket("/ws/terminal")
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
    if not os.path.exists(main_cpp_path) or os.path.getsize(main_cpp_path) == 0:
        with open(main_cpp_path, "w") as f:
            f.write("#include <iostream>\n\nint main() {\n    std::cout << \"Hello from Sandbox!\\n\";\n    return 0;\n}\n")

    session = DebugSession(session_id, "", user_sandbox, user_id=user["id"] if user else None)
    session.terminal_ws = ws 
    sessions[session_id] = session
    
    await ws.send_text(f"SESSION_ID:{session_id}")

    try:
        container = docker_client.containers.run(
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
        sessions.pop(session_id, None)
        await ws.send_text(f"Error starting container: {exc}\r\n")
        await ws.close()
        return

    mi_exec_info = docker_client.api.exec_create(
        container.id,
        cmd=["sh", "-c", "stty -echo && tty && sleep infinity"],
        stdin=True, stdout=True, stderr=True, tty=True
    )
    mi_reader, mi_writer = await open_exec_socket(mi_exec_info["Id"], tty=True)
    
    mi_tty_bytes = await mi_reader.readuntil(b'\n')
    session.mi_tty = mi_tty_bytes.decode('utf-8').strip()

    try:
        await session.connect_gdb(mi_reader, mi_writer)
    except Exception as exc:
        print(f"[Session] GDB connect error: {exc}")

    exec_info = docker_client.api.exec_create(
        container.id,
        cmd=["/bin/bash"],
        stdin=True,
        stdout=True,
        stderr=True,
        tty=True,
    )

    bash_reader, bash_writer = await open_exec_socket(exec_info["Id"], tty=True)
    session.bash_writer = bash_writer

    async def docker_to_ws():
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


@router.websocket("/ws/dbg/{session_id}")
async def websocket_dbg(ws: WebSocket, session_id: str):
    await ws.accept()

    session = sessions.get(session_id)
    if session is None:
        await ws.send_json({"type": "error", "payload": "Session not found or container not ready."})
        await ws.close()
        return

    session.last_active = time.time()
    await ws.send_json({"type": "state_update", "payload": session.gdb.state.serialize()})

    async def forward_events():
        while session.alive:
            try:
                event = await asyncio.wait_for(session.event_queue.get(), timeout=1.0)
                await ws.send_json(event)
            except asyncio.TimeoutError:
                continue
            except (WebSocketDisconnect, asyncio.CancelledError):
                break
            except Exception as exc:
                print(f"[DBG Forward] Error: {exc}")
                break

    async def receive_commands():
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

                command_map = {
                    "-exec-run": ("run", b"run\r"),
                    "-exec-continue": ("continue", b"continue\r"),
                    "-exec-interrupt": ("^C", b"\x03"),
                    "-exec-step": ("step", b"step\r"),
                    "-exec-next": ("next", b"next\r"),
                    "-exec-next --reverse": ("reverse-next", b"reverse-next\r"),
                    "-exec-step --reverse": ("reverse-step", b"reverse-step\r"),
                }

                if cmd == "COMPILE_AND_RUN":
                    breakpoints = data.get("breakpoints", [])
                    asyncio.create_task(_compile_and_run(session, ws, breakpoints))

                elif cmd == "STOP_EXECUTION":
                    if session.bash_writer and not session.bash_writer.is_closing():
                        session.bash_writer.write(b"quit\r")
                        await session.bash_writer.drain()
                    gdb.state.status = "idle"
                    gdb.state.threads = []
                    gdb.state.stack = []
                    gdb.state.locals = []
                    gdb.state.current_frame = None
                    await gdb._broadcast_state()
                
                elif cmd in command_map:
                    echo_str, write_bytes = command_map[cmd]
                    if session.bash_writer:
                        await echo_to_term(echo_str)
                        session.bash_writer.write(write_bytes)
                        await session.bash_writer.drain()

                else:
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
    if session.gdb.state.status != "idle":
        if session.bash_writer and not session.bash_writer.is_closing():
            session.bash_writer.write(b"quit\r")
            await session.bash_writer.drain()
            await asyncio.sleep(0.15)

    if breakpoints is None:
        breakpoints = []
    loop = asyncio.get_running_loop()
    try:
        def _compile():
            c = docker_client.containers.get(session.container_id)
            c.exec_run("pkill -9 gdb") # kill all debug session before the next gdb session starts
            return c.exec_run("g++ -g main.cpp -o main", workdir="/workspace")

        res = await loop.run_in_executor(None, _compile)
        if res.exit_code != 0:
            await session.event_queue.put({
                "type": "error",
                "payload": f"Compilation failed:\n{res.output.decode()}"
            })
            return

        gdb = session.gdb
        gdb.state = DebugState()

        gdb_cmd = f"gdb -q -ex 'new-ui mi3 {session.mi_tty}'"
        gdb_cmd += f" -ex 'set confirm off'"
        gdb_cmd += f" -ex 'break main'"
        for bp_line in breakpoints:
            gdb_cmd += f" -ex 'break main.cpp:{bp_line}'"
        gdb_cmd += " ./main\r"

        if session.bash_writer and not session.bash_writer.is_closing():
            session.bash_writer.write(gdb_cmd.encode('utf-8'))
            
        await asyncio.sleep(0.5)
        if session.bash_writer and not session.bash_writer.is_closing():
            session.bash_writer.write(b"run\r")

    except Exception as exc:
        import traceback
        await session.event_queue.put({
            "type": "error",
            "payload": f"Compile/run error: {exc}\n{traceback.format_exc()}"
        })
