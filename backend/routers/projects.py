import os
import shutil
import sqlite3
from typing import Optional
from fastapi import APIRouter, Cookie, HTTPException

from backend.config import DB_PATH, DATA_USERS_DIR
from backend.models import ProjectPayload
from backend.dependencies import get_current_user_id

router = APIRouter()

@router.get("/api/projects")
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

@router.post("/api/projects")
async def create_project(payload: ProjectPayload, session_token: Optional[str] = Cookie(None)):
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

@router.put("/api/projects/{project_id}")
async def update_project(project_id: int, payload: ProjectPayload, session_token: Optional[str] = Cookie(None)):
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

@router.delete("/api/projects/{project_id}")
async def delete_project(project_id: int, session_token: Optional[str] = Cookie(None)):
    user = await get_current_user_id(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM projects WHERE id = ? AND user_id = ?", (project_id, user["id"]))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
            
        cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        
    project_dir = os.path.abspath(os.path.join(DATA_USERS_DIR, str(user["id"]), str(project_id)))
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)
        
    return {"status": "ok"}
