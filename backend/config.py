import os

DB_PATH = "/tmp/data/app.db"
DATA_USERS_DIR = "/tmp/data/users"
SANDBOXES_DIR = "/tmp/sandboxes"
SESSION_TIMEOUT = 600

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(DATA_USERS_DIR, exist_ok=True)
os.makedirs(SANDBOXES_DIR, exist_ok=True)
