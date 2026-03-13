"""Configuration for the Initiative Engine."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
RULES_DIR = BASE_DIR / "rules"
DATA_DIR = BASE_DIR / "data"

# SQLite databases
SIGNALS_DB = DATA_DIR / "signals.db"
HISTORY_DB = DATA_DIR / "history.db"

# Engine defaults
DEFAULT_SIGNAL_TTL_MINUTES = 1440  # 24 hours
MAX_SIGNAL_BUFFER_SIZE = 10000
ENGINE_POLL_INTERVAL_SECONDS = 60

# Ensure data dir exists
DATA_DIR.mkdir(exist_ok=True)
