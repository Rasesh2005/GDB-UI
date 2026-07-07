import sqlite3
import hashlib
from backend.config import DB_PATH

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                theme TEXT DEFAULT 'vs-dark'
            )
        ''')
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cur.fetchall()]
        if 'theme' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN theme TEXT DEFAULT 'vs-dark'")
            
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, name)
            )
        ''')
        conn.commit()

def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), b'gdbuisalt', 100000
    ).hex()
