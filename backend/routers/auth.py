import sqlite3
import secrets
from typing import Optional
from fastapi import APIRouter, Response, Cookie, HTTPException

from backend.config import DB_PATH
from backend.models import UserCreate
from backend.database import hash_password
from backend.dependencies import get_current_user_id

router = APIRouter()

@router.post("/api/register")
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

@router.post("/api/login")
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

@router.post("/api/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(None)):
    if session_token:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (session_token,))
            conn.commit()
            
    response.delete_cookie(key="session_token", path="/")
    return {"status": "ok"}

@router.get("/api/me")
async def get_me(session_token: Optional[str] = Cookie(None)):
    user = await get_current_user_id(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT theme FROM users WHERE id = ?", (user["id"],))
        row = cur.fetchone()
        theme = row[0] if row else "vs-dark"
        
    return {"username": user["username"], "theme": theme}

@router.post("/api/user/theme")
async def update_theme(payload: dict, session_token: Optional[str] = Cookie(None)):
    user = await get_current_user_id(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    theme = payload.get("theme", "vs-dark")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE users SET theme = ? WHERE id = ?", (theme, user["id"]))
        conn.commit()
    return {"status": "ok"}
