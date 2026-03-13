"""Authentication helpers for connectors."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional


class AuthHelper:
    """Utilities for common auth patterns."""

    @staticmethod
    def load_json_credentials(path: str | Path) -> dict:
        """Load credentials from a JSON file."""
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"Credentials file not found: {p}")
        return json.loads(p.read_text())

    @staticmethod
    def get_env_token(var_name: str) -> Optional[str]:
        """Get a token from environment variable."""
        return os.environ.get(var_name)

    @staticmethod
    def get_gh_token() -> Optional[str]:
        """Get GitHub token from gh CLI auth."""
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return None

    @staticmethod
    def check_gog_auth() -> bool:
        """Check if gog CLI is authenticated by running a quick test command."""
        # Config location varies — just test the CLI directly
        try:
            result = subprocess.run(
                ["gog", "gmail", "list", "--json", "--results-only", "in:inbox newer_than:1d"],
                capture_output=True, text=True, timeout=15,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    @staticmethod
    def run_cli(cmd: list[str], timeout: int = 30) -> tuple[bool, str]:
        """Run a CLI command and return (success, output)."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=timeout,
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            return result.returncode == 0, output.strip()
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except FileNotFoundError:
            return False, f"Command not found: {cmd[0]}"
        except Exception as e:
            return False, str(e)
