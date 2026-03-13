"""Configuration for Percept Knowledge Graph."""
import os
from pathlib import Path

# Paths
KG_ROOT = Path(__file__).parent
DATA_DIR = KG_ROOT / "data"
DB_PATH = DATA_DIR / "graph.db"

# Workspace (source files)
WORKSPACE = Path(os.environ.get("PERCEPT_WORKSPACE", "/Users/jarvis/.openclaw/workspace"))

# Source files for ingestion
SOURCES = {
    "memory": WORKSPACE / "MEMORY.md",
    "user": WORKSPACE / "USER.md",
    "tools": WORKSPACE / "TOOLS.md",
    "decisions": WORKSPACE / "decisions.md",
    "lessons": WORKSPACE / "memory" / "lessons.md",
    "code_ids": WORKSPACE / "vectorcare-code-identities.md",
    "daily_dir": WORKSPACE / "memory",
}

# Ensure data dir exists
DATA_DIR.mkdir(parents=True, exist_ok=True)
