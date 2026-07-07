import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.database import init_db
from backend.gdb.session import cleanup_stale_sessions
from backend.routers.auth import router as auth_router
from backend.routers.projects import router as projects_router
from backend.routers.execution import router as execution_router
from backend.routers.websockets import router as websockets_router

init_db()

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(cleanup_stale_sessions())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)
app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")

@app.get("/")
async def serve_index():
    return FileResponse("frontend/dist/index.html")

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(execution_router)
app.include_router(websockets_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
