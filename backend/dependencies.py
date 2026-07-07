import sqlite3
from typing import Optional
from fastapi import Cookie
from backend.config import DB_PATH

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
