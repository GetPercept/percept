#!/usr/bin/env python3
"""Wrapper to run Percept MCP server with correct sys.path."""
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.mcp_server import run
run()
