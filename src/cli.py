#!/usr/bin/env python3
"""Percept CLI — standalone voice-to-action pipeline controller.

Usage:
    percept listen    Start audio pipeline, output protocol events
    percept serve     Start full server (receiver + API + dashboard)
    percept status    Show pipeline status
    percept transcripts  List recent transcripts
    percept actions   List recent actions
    percept config    Show/edit configuration
"""

import argparse
import json
import os
import sys
import time
import glob
import re
import subprocess
from datetime import datetime, date
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── Paths ──────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONVERSATIONS_DIR = DATA_DIR / "conversations"
SUMMARIES_DIR = DATA_DIR / "summaries"
CONFIG_FILE = BASE_DIR / "config" / "config.json"
LIVE_FILE = Path("/tmp/percept-live.txt")

# ── ANSI Colors ────────────────────────────────────────────────────────

class C:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    BLUE = "\033[34m"
    RESET = "\033[0m"

    @staticmethod
    def strip():
        """Disable colors if not a TTY."""
        if not sys.stdout.isatty():
            for attr in ["BOLD", "DIM", "GREEN", "RED", "YELLOW", "CYAN", "MAGENTA", "BLUE", "RESET"]:
                setattr(C, attr, "")

C.strip()

# ── Helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(cfg: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def check_health(port: int = 8900) -> dict | None:
    try:
        resp = urlopen(f"http://localhost:{port}/health", timeout=2)
        return json.loads(resp.read())
    except Exception:
        return None


def count_words_in_file(path: Path) -> int:
    try:
        return len(path.read_text().split())
    except Exception:
        return 0


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.0f}m {seconds % 60:.0f}s"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"


def parse_timestamp_from_filename(name: str) -> datetime | None:
    """Extract datetime from filenames like 2026-02-20_14-53-45_conversation.md or 2026-02-20_13-52.md"""
    patterns = [
        (r"(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})", "%Y-%m-%d_%H-%M-%S"),
        (r"(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})", "%Y-%m-%d_%H-%M"),
    ]
    for pat, fmt in patterns:
        m = re.search(pat, name)
        if m:
            try:
                return datetime.strptime(m.group(0), fmt)
            except ValueError:
                pass
    return None

# ── Commands ───────────────────────────────────────────────────────────

def cmd_status(args):
    """Show pipeline status."""
    print(f"\n{C.BOLD}{C.CYAN}⦿ Percept Status{C.RESET}\n")

    # Server health
    cfg = load_config()
    port = cfg.get("server", {}).get("port", 8900)
    health = check_health(port)
    if health:
        print(f"  {C.GREEN}●{C.RESET} Server        {C.GREEN}running{C.RESET} on port {port}")
        uptime = health.get("uptime")
        if uptime:
            print(f"  {C.DIM}  Uptime:       {format_duration(uptime)}{C.RESET}")
    else:
        print(f"  {C.RED}●{C.RESET} Server        {C.RED}not running{C.RESET}")

    # Live file
    if LIVE_FILE.exists():
        mtime = LIVE_FILE.stat().st_mtime
        age = time.time() - mtime
        if age < 120:
            print(f"  {C.GREEN}●{C.RESET} Live stream   {C.GREEN}active{C.RESET} (updated {format_duration(age)} ago)")
        else:
            print(f"  {C.YELLOW}●{C.RESET} Live stream   {C.YELLOW}stale{C.RESET} (updated {format_duration(age)} ago)")
    else:
        print(f"  {C.DIM}○{C.RESET} Live stream   {C.DIM}no data{C.RESET}")

    # Today's conversations
    today_str = date.today().strftime("%Y-%m-%d")
    today_convos = []
    total_words = 0
    if CONVERSATIONS_DIR.exists():
        for f in sorted(CONVERSATIONS_DIR.iterdir()):
            if f.name.startswith(today_str) and f.suffix == ".md":
                today_convos.append(f)
                total_words += count_words_in_file(f)

    # Also check memory/conversations
    mem_convos_dir = BASE_DIR / "memory" / "conversations"
    if mem_convos_dir.exists():
        for f in sorted(mem_convos_dir.iterdir()):
            if f.name.startswith(today_str) and f.suffix == ".md":
                today_convos.append(f)
                total_words += count_words_in_file(f)

    print(f"\n  {C.BOLD}Today{C.RESET}")
    print(f"  Conversations:  {C.BOLD}{len(today_convos)}{C.RESET}")
    print(f"  Words captured: {C.BOLD}{total_words:,}{C.RESET}")

    # Summaries
    today_summaries = []
    if SUMMARIES_DIR.exists():
        for f in sorted(SUMMARIES_DIR.iterdir()):
            if f.name.startswith(today_str):
                today_summaries.append(f)
    print(f"  Summaries:      {C.BOLD}{len(today_summaries)}{C.RESET}")

    # Last event
    all_files = list(today_convos) + list(today_summaries)
    if all_files:
        latest = max(all_files, key=lambda f: f.stat().st_mtime)
        age = time.time() - latest.stat().st_mtime
        print(f"  Last event:     {C.DIM}{format_duration(age)} ago{C.RESET}")

    print()


def cmd_transcripts(args):
    """List recent transcripts."""
    dirs = [CONVERSATIONS_DIR, BASE_DIR / "memory" / "conversations"]
    files = []
    for d in dirs:
        if d.exists():
            files.extend(f for f in d.iterdir() if f.suffix == ".md")

    # Filter
    if args.today:
        today_str = date.today().strftime("%Y-%m-%d")
        files = [f for f in files if f.name.startswith(today_str)]

    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    if args.search:
        query = args.search.lower()
        files = [f for f in files if query in f.read_text().lower()]

    files = files[: args.limit]

    if not files:
        print(f"{C.DIM}No transcripts found.{C.RESET}")
        return

    print(f"\n{C.BOLD}{C.CYAN}📝 Recent Transcripts{C.RESET}\n")
    for f in files:
        ts = parse_timestamp_from_filename(f.name)
        ts_str = ts.strftime("%H:%M") if ts else "??:??"
        date_str = ts.strftime("%Y-%m-%d") if ts else ""
        words = count_words_in_file(f)
        preview = f.read_text().strip().split("\n")
        # Get first non-header line
        first_line = ""
        for line in preview:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
                first_line = stripped[:80]
                break

        print(f"  {C.DIM}{date_str}{C.RESET} {C.BOLD}{ts_str}{C.RESET}  {C.DIM}{words:>5} words{C.RESET}  {first_line}")

    print()


def cmd_actions(args):
    """List recent actions."""
    # Look for action files in data dir
    actions_dir = DATA_DIR / "actions"
    if not actions_dir.exists():
        print(f"\n{C.BOLD}{C.CYAN}⚡ Recent Actions{C.RESET}\n")
        print(f"  {C.DIM}No actions recorded yet.{C.RESET}\n")
        return

    files = sorted(actions_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)[:20]
    print(f"\n{C.BOLD}{C.CYAN}⚡ Recent Actions{C.RESET}\n")
    for f in files:
        try:
            data = json.loads(f.read_text())
            status = data.get("status", "unknown")
            intent = data.get("intent", "?")
            ts = data.get("timestamp", "")[:16]
            color = {
                "executed": C.GREEN,
                "pending": C.YELLOW,
                "failed": C.RED,
                "needs_human": C.MAGENTA,
            }.get(status, C.DIM)
            print(f"  {color}●{C.RESET} {ts}  {C.BOLD}{intent}{C.RESET}  {color}{status}{C.RESET}")
        except Exception:
            pass
    print()


def cmd_search(args):
    """Semantic search over conversations."""
    from src.vector_store import PerceptVectorStore
    vs = PerceptVectorStore()

    if not vs._get_table():
        print(f"{C.RED}No vector index found. Run: PYTHONPATH=. .venv/bin/python scripts/index_vectors.py{C.RESET}")
        return

    results = vs.search(args.query, limit=args.limit, date_filter=args.date)
    if not results:
        print(f"{C.DIM}No results for: {args.query}{C.RESET}")
        return

    print(f"\n{C.BOLD}{C.CYAN}🔍 Search: {args.query}{C.RESET}\n")
    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        date = r.get("date", "")
        cid = r.get("conversation_id", "")
        ctype = r.get("chunk_type", "")
        text = r.get("text", "").replace("\n", " ")[:120]
        speakers = r.get("speakers", "[]")
        if isinstance(speakers, str):
            try:
                speakers = json.loads(speakers)
            except Exception:
                speakers = []
        spk_str = ", ".join(speakers) if speakers else ""

        score_color = C.GREEN if score < 0.5 else C.YELLOW if score < 1.0 else C.DIM
        print(f"  {C.BOLD}{i}.{C.RESET} {score_color}[{score:.3f}]{C.RESET} {C.DIM}{date}{C.RESET} {C.DIM}({ctype}){C.RESET}")
        if spk_str:
            print(f"     {C.DIM}Speakers: {spk_str}{C.RESET}")
        print(f"     {text}")
        print()


def cmd_config(args):
    """Show or edit config."""
    cfg = load_config()

    if args.set:
        key, _, value = args.set.partition("=")
        if not value:
            print(f"{C.RED}Usage: --set key=value{C.RESET}")
            return
        # Support dotted keys like server.port
        parts = key.split(".")
        obj = cfg
        for p in parts[:-1]:
            obj = obj.setdefault(p, {})
        # Try to parse as int/float/bool
        if value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False
        else:
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass
        obj[parts[-1]] = value
        save_config(cfg)
        print(f"{C.GREEN}✓{C.RESET} Set {C.BOLD}{key}{C.RESET} = {value}")
        return

    # Show config
    print(f"\n{C.BOLD}{C.CYAN}⚙ Configuration{C.RESET}\n")
    print(f"  {C.DIM}File: {CONFIG_FILE}{C.RESET}\n")
    print(json.dumps(cfg, indent=2))
    print()


def cmd_listen(args):
    """Start audio pipeline and output protocol events."""
    # Import here so the CLI loads fast for other commands
    try:
        import uvicorn
    except ImportError:
        print(f"{C.RED}Error:{C.RESET} uvicorn not installed. Run: pip install uvicorn fastapi")
        sys.exit(1)

    print(f"{C.BOLD}{C.CYAN}⦿ Percept Listen{C.RESET}", file=sys.stderr)
    print(f"  Agent:     {C.BOLD}{args.agent}{C.RESET}", file=sys.stderr)
    print(f"  Port:      {args.port}", file=sys.stderr)
    print(f"  Wake word: {args.wake_word}", file=sys.stderr)
    print(f"  Format:    {args.format}", file=sys.stderr)
    print(file=sys.stderr)

    # Set env vars for the receiver to pick up
    os.environ["PERCEPT_AGENT"] = args.agent
    os.environ["PERCEPT_FORMAT"] = args.format
    os.environ["PERCEPT_WAKE_WORD"] = args.wake_word
    if args.webhook_url:
        os.environ["PERCEPT_WEBHOOK_URL"] = args.webhook_url

    # Start the FastAPI receiver
    uvicorn.run(
        "src.receiver:app",
        host="0.0.0.0",
        port=args.port,
        log_level="warning",
    )


def cmd_serve(args):
    """Start full server with dashboard."""
    try:
        import uvicorn
    except ImportError:
        print(f"{C.RED}Error:{C.RESET} uvicorn not installed. Run: pip install uvicorn fastapi")
        sys.exit(1)

    print(f"{C.BOLD}{C.CYAN}⦿ Percept Server{C.RESET}", file=sys.stderr)
    print(f"  Receiver:  port {args.port}", file=sys.stderr)
    print(f"  Dashboard: port {args.dashboard_port}", file=sys.stderr)
    print(file=sys.stderr)

    # Start dashboard in background
    dashboard_script = BASE_DIR / "dashboard" / "server.py"
    if dashboard_script.exists():
        subprocess.Popen(
            [sys.executable, str(dashboard_script), "--port", str(args.dashboard_port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"  {C.GREEN}●{C.RESET} Dashboard started on http://localhost:{args.dashboard_port}", file=sys.stderr)

    uvicorn.run(
        "src.receiver:app",
        host="0.0.0.0",
        port=args.port,
        log_level="info",
    )

def cmd_audit(args):
    """Show data stats."""
    from src.database import PerceptDB
    db = PerceptDB()
    stats = db.audit()
    db.close()

    print(f"\n{C.BOLD}{C.CYAN}📊 Percept Data Audit{C.RESET}\n")
    for table, count in stats.items():
        if table == "storage_bytes":
            size_mb = count / (1024 * 1024)
            print(f"  {C.BOLD}Storage:{C.RESET}        {size_mb:.2f} MB")
        else:
            label = table.replace("_", " ").title()
            print(f"  {C.BOLD}{label}:{C.RESET}  {count:>8,}")
    print()


def cmd_purge(args):
    """Purge data."""
    from src.database import PerceptDB
    db = PerceptDB()

    if args.conversation:
        db.purge_conversation(args.conversation)
        print(f"{C.GREEN}✓{C.RESET} Purged conversation {args.conversation}")
    elif args.older_than:
        count = db.purge_older_than(args.older_than)
        print(f"{C.GREEN}✓{C.RESET} Purged {count} conversations older than {args.older_than} days")
    elif args.all:
        if not args.confirm:
            print(f"{C.RED}Error:{C.RESET} Use --confirm to delete all data")
            db.close()
            return
        # Purge everything
        with db._lock:
            for table in ("utterances", "entity_mentions", "actions", "relationships", "conversations"):
                db._conn.execute(f"DELETE FROM {table}")
            db._conn.commit()
        print(f"{C.GREEN}✓{C.RESET} Purged all data")
    else:
        # Purge expired TTL
        count = db.purge_expired()
        print(f"{C.GREEN}✓{C.RESET} Purged {count} expired conversations")

    db.close()


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="percept",
        description="Percept — ambient voice intelligence pipeline",
    )
    sub = parser.add_subparsers(dest="command")

    # listen
    p_listen = sub.add_parser("listen", help="Start audio pipeline, output protocol events")
    p_listen.add_argument("--agent", choices=["openclaw", "stdout", "webhook"], default="openclaw")
    p_listen.add_argument("--webhook-url", default=None)
    p_listen.add_argument("--wake-word", default="Hey Jarvis")
    p_listen.add_argument("--port", type=int, default=8900)
    p_listen.add_argument("--format", choices=["json", "text"], default="json")

    # serve
    p_serve = sub.add_parser("serve", help="Start full server (receiver + dashboard)")
    p_serve.add_argument("--port", type=int, default=8900)
    p_serve.add_argument("--dashboard-port", type=int, default=8960)
    p_serve.add_argument("--webhook-url", default=None)

    # status
    sub.add_parser("status", help="Show pipeline status")

    # transcripts
    p_trans = sub.add_parser("transcripts", help="List recent transcripts")
    p_trans.add_argument("--today", action="store_true")
    p_trans.add_argument("--search", default=None)
    p_trans.add_argument("--limit", type=int, default=20)

    # actions
    sub.add_parser("actions", help="List recent actions")

    # search
    p_search = sub.add_parser("search", help="Semantic search over conversations")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--date", default=None, help="Filter by date (YYYY-MM-DD)")

    # config
    p_cfg = sub.add_parser("config", help="Show/edit configuration")
    p_cfg.add_argument("--set", default=None, metavar="KEY=VALUE")
    p_cfg.add_argument("--show", action="store_true")

    # audit
    sub.add_parser("audit", help="Show data stats (conversations, utterances, speakers, etc.)")

    # purge
    p_purge = sub.add_parser("purge", help="Purge data")
    p_purge.add_argument("--older-than", type=int, default=None, metavar="DAYS", help="Delete conversations older than N days")
    p_purge.add_argument("--conversation", default=None, metavar="ID", help="Delete a specific conversation")
    p_purge.add_argument("--all", action="store_true", help="Delete all data")
    p_purge.add_argument("--confirm", action="store_true", help="Confirm destructive action")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmds = {
        "listen": cmd_listen,
        "serve": cmd_serve,
        "status": cmd_status,
        "transcripts": cmd_transcripts,
        "actions": cmd_actions,
        "config": cmd_config,
        "search": cmd_search,
        "audit": cmd_audit,
        "purge": cmd_purge,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
