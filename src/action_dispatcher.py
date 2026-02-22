"""OpenClaw CLI dispatch, action saving, and voice action routing for Percept.

Handles forwarding voice commands to OpenClaw, saving actions to the database,
and routing different action types.
"""

import asyncio
import json
import logging
import os
import re
import shutil
from typing import Optional

from src.database import PerceptDB

logger = logging.getLogger(__name__)

# Binary path resolution with fallback
def _get_binary_path(name: str) -> str:
    """Get binary path dynamically with fallback."""
    path = shutil.which(name)
    if not path:
        logger.warning(f"Binary '{name}' not found in PATH, action will be skipped")
        return None
    return path


async def dispatch_to_openclaw(message: str, timeout: int = 30) -> tuple[bool, str]:
    """Send a message to OpenClaw via CLI.

    Args:
        message: The message/command to send.
        timeout: Timeout in seconds for the CLI call.

    Returns:
        Tuple of (success: bool, output: str).
    """
    try:
        openclaw_path = _get_binary_path("openclaw")
        if not openclaw_path:
            return False, "openclaw binary not found"
            
        env = os.environ.copy()  # Inherit system PATH
        proc = await asyncio.create_subprocess_exec(
            openclaw_path, "agent", "--message", message, "--to", "+1XXXXXXXXXX",  # TODO: load from config
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode == 0:
            return True, stdout.decode()[:500]
        else:
            return False, stderr.decode()[:500]
    except asyncio.TimeoutError:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


async def send_imessage(text: str):
    """Send iMessage directly via imsg CLI.

    Args:
        text: Message text to send.
    """
    try:
        imsg_path = _get_binary_path("imsg")
        if not imsg_path:
            logger.warning("imsg binary not found, skipping message")
            return
            
        env = os.environ.copy()  # Inherit system PATH
        proc = await asyncio.create_subprocess_exec(
            imsg_path, "send", "--to", "+1XXXXXXXXXX", "--text", text,  # TODO: load from config
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        await asyncio.wait_for(proc.communicate(), timeout=15)
    except Exception as e:
        logger.error(f"iMessage send failed: {e}")


def save_action_to_db(db: PerceptDB, action_data: dict, raw_text: str,
                      conversation_id: str = None) -> Optional[str]:
    """Save a parsed voice action to the database.

    Args:
        db: PerceptDB instance.
        action_data: Parsed action dict with 'action' key and params.
        raw_text: Original command text.
        conversation_id: Associated conversation ID.

    Returns:
        Action ID string, or None on failure.
    """
    try:
        return db.save_action(
            conversation_id=conversation_id,
            intent=action_data.get("action", "unknown"),
            params=action_data,
            raw_text=raw_text,
        )
    except Exception as e:
        logger.error(f"Failed to save action to DB: {e}")
        return None


def extract_command_after_wake(text: str) -> str:
    """Extract the command portion after a wake word.

    Args:
        text: Full text that may contain a wake word prefix.

    Returns:
        Cleaned command text with wake word removed.
    """
    clean = text
    match = re.search(r'(?:hey[,.]?\s*)?jarvis[,.\s]*', clean, re.IGNORECASE)
    if match:
        clean = clean[match.end():].strip()
    return clean.strip('.,!? ')
