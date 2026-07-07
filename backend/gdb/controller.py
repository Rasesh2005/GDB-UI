import asyncio
from typing import Any, Dict
from pygdbmi.gdbmiparser import parse_response

from backend.models import DebugState

class AsyncGdbController:
    """
    Manages the async streaming connection to GDB/MI running inside Docker.
    """

    def __init__(self, event_queue: asyncio.Queue):
        self.event_queue = event_queue
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._token = 1
        self._pending: Dict[int, asyncio.Future] = {}
        self._raw_queue: asyncio.Queue = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None
        self._dispatch_task: asyncio.Task | None = None
        self._alive = True
        self.state: DebugState = DebugState()

    async def connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._reader = reader
        self._writer = writer
        self._reader_task = asyncio.create_task(self._gdb_reader_loop())
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())

    async def _gdb_reader_loop(self):
        line_buf = b""
        try:
            while self._alive:
                try:
                    chunk = await asyncio.wait_for(
                        self._reader.read(4096), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    continue

                if not chunk:
                    break

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

    async def _dispatch_loop(self):
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

                if rtype == "result":
                    if token is not None and token in self._pending:
                        fut = self._pending.pop(token)
                        if not fut.done():
                            fut.set_result(record)
                    await self._handle_async_record(rtype, message, payload)

                elif rtype in ("exec", "notify"):
                    await self._handle_async_record(rtype, message, payload)

                elif rtype in ("console", "target", "log"):
                    if payload and isinstance(payload, str) and "Process record: failed to record execution log" in payload:
                        if getattr(self.state, 'recording', False):
                            self.state.recording = False
                            await self.send_fire('-interpreter-exec console "record stop"')
                            await self.send_fire('-exec-continue')

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            import traceback
            await self.event_queue.put({
                "type": "error",
                "payload": f"Dispatch error: {exc}\n{traceback.format_exc()}"
            })

    async def _handle_async_record(self, rtype: str, message: str, payload: Any):
        if message == "stopped":
            reason = payload.get("reason", "")
            if reason in ("exited-normally", "exited", "exited-signalled"):
                self.state.status = "idle"
                self.state.threads = []
                self.state.stack = []
                self.state.locals = []
                self.state.current_frame = None
                await self._broadcast_state()
                return

            self.state.status = "stopped"
            if not getattr(self.state, 'recording', False):
                await self.send_fire('-interpreter-exec console "record full"')
                self.state.recording = True
            await self._broadcast_state()
            asyncio.create_task(self._sync_full_state())
        elif message == "running":
            self.state.status = "running"
            await self._broadcast_state()
        elif message in ("thread-created", "thread-exited", "breakpoint-created", "breakpoint-deleted", "breakpoint-modified"):
            asyncio.create_task(self._sync_full_state())

    async def send_command(self, cmd: str, timeout: float = 5.0) -> dict | None:
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

    async def send_fire(self, cmd: str):
        if not self._writer or self._writer.is_closing():
            return
        line = f"{cmd}\n"
        try:
            self._writer.write(line.encode())
            await self._writer.drain()
        except Exception as exc:
            print(f"[GDB Fire] Error sending '{cmd}': {exc}")

    async def _sync_full_state(self):
        try:
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
            await self._broadcast_state()

    async def _broadcast_state(self):
        await self.event_queue.put({
            "type": "state_update",
            "payload": self.state.serialize(),
        })

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
