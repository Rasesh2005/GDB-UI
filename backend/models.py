from typing import Any, Dict
from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    password: str

class CodeExecutionRequest(BaseModel):
    code: str
    input: str

class ProjectPayload(BaseModel):
    name: str

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
