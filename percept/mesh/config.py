"""Percept Mesh configuration."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "team.db"
DEFAULT_PORT = 8070
DEFAULT_HOST = "0.0.0.0"
DEFAULT_SYNC_INTERVAL = 300  # seconds

# Presence thresholds (seconds)
PRESENCE_ONLINE = 120    # < 2 min since heartbeat
PRESENCE_IDLE = 600      # 2-10 min
# > PRESENCE_IDLE = offline

# Server URL (agents configure this to point at the team server)
SERVER_URL = os.environ.get("PERCEPT_MESH_URL", f"http://127.0.0.1:{DEFAULT_PORT}")
API_KEY = os.environ.get("PERCEPT_MESH_KEY", "")
