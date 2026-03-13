"""Agent online/offline/last-seen status management."""
import time
import threading
import requests
from typing import Optional


class PresenceManager:
    """Manages agent presence (heartbeat) with the team server."""
    
    def __init__(self, server_url: str, api_key: str, interval: int = 60):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
    
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
    
    def send_heartbeat(self, status: str = "online") -> bool:
        """Send a single heartbeat to the server."""
        try:
            resp = requests.post(
                f"{self.server_url}/api/presence/heartbeat",
                json={"status": status},
                headers=self._headers(),
                timeout=10,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False
    
    def _heartbeat_loop(self):
        """Background loop that sends heartbeats."""
        while not self._stop_event.is_set():
            self.send_heartbeat("online")
            self._stop_event.wait(self.interval)
    
    def start(self):
        """Start background heartbeat."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop background heartbeat."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
    
    def get_team_presence(self) -> list[dict]:
        """Fetch presence info for all team members."""
        try:
            resp = requests.get(
                f"{self.server_url}/api/presence",
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("presence", [])
            return []
        except requests.RequestException:
            return []
    
    @staticmethod
    def format_presence(members: list[dict]) -> str:
        """Format presence info for display."""
        if not members:
            return "No team members found."
        
        icons = {"online": "🟢", "idle": "🟡", "offline": "🔴"}
        lines = []
        for m in members:
            icon = icons.get(m.get("status", "offline"), "⚪")
            name = m.get("name", "unknown")
            role = m.get("role", "member")
            last_seen = m.get("last_seen", "never")
            lines.append(f"  {icon} {name} ({role}) — last seen: {last_seen}")
        
        return "Team Presence:\n" + "\n".join(lines)
