import asyncio
import time
from typing import Optional, Dict

from backend.gdb.controller import AsyncGdbController
from backend.config import SESSION_TIMEOUT

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
        self.terminal_ws = None 

    async def connect_gdb(self, reader, writer):
        await self.gdb.connect(reader, writer)

    async def stop(self):
        self.alive = False
        await self.gdb.close()

sessions: Dict[str, DebugSession] = {}

async def cleanup_stale_sessions():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        stale = [sid for sid, s in list(sessions.items())
                 if now - s.last_active > SESSION_TIMEOUT]
        for sid in stale:
            print(f"[Session] Cleaning up stale session: {sid}")
            await sessions[sid].stop()
            del sessions[sid]
