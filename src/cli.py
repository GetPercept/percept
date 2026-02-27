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
    """Load Percept YAML configuration from the default path."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(cfg: dict):
    """Save configuration dict to the YAML config file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def check_health(port: int = 8900) -> dict | None:
    """Check if the Percept server is running and healthy."""
    try:
        resp = urlopen(f"http://localhost:{port}/health", timeout=2)
        return json.loads(resp.read())
    except Exception:
        return None


def count_words_in_file(path: Path) -> int:
    """Count the number of words in a text file."""
    try:
        return len(path.read_text().split())
    except Exception:
        return 0


def format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
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
    """Search over conversations with multiple modes."""
    from src.vector_store import PerceptVectorStore
    from src.database import PerceptDB
    
    vs = PerceptVectorStore()
    db = PerceptDB()

    # Determine search mode
    mode = getattr(args, 'mode', 'hybrid')
    
    if mode == "keyword":
        # FTS5 keyword search only
        results = db.search_utterances(args.query, limit=args.limit)
        db.close()
        
        # Convert to standard format
        formatted_results = []
        for i, r in enumerate(results):
            formatted_results.append({
                "conversation_id": r.get("conversation_id", ""),
                "text": r.get("text", ""),
                "score": 1.0 / (i + 1),
                "date": "",
                "speakers": "[]", 
                "chunk_type": "keyword",
                "source": "keyword"
            })
        results = formatted_results
        
    elif mode == "semantic":
        # Vector semantic search only
        if not vs._get_table():
            print(f"{C.RED}No vector index found. Run: percept reindex{C.RESET}")
            db.close()
            return
        results = vs.search(args.query, limit=args.limit, date_filter=args.date)
        
    else:  # hybrid (default)
        # Hybrid search
        if not vs._get_table():
            print(f"{C.YELLOW}No vector index found, falling back to keyword search. Run: percept reindex{C.RESET}")
            results = db.search_utterances(args.query, limit=args.limit)
            db.close()
            # Convert to standard format
            formatted_results = []
            for i, r in enumerate(results):
                formatted_results.append({
                    "conversation_id": r.get("conversation_id", ""),
                    "text": r.get("text", ""),
                    "score": 1.0 / (i + 1),
                    "date": "",
                    "speakers": "[]",
                    "chunk_type": "keyword", 
                    "source": "keyword"
                })
            results = formatted_results
        else:
            results = vs.hybrid_search(args.query, limit=args.limit, alpha=0.5, date_filter=args.date)
    
    db.close()

    if not results:
        print(f"{C.DIM}No results for: {args.query}{C.RESET}")
        return

    mode_emoji = {"keyword": "📝", "semantic": "🧠", "hybrid": "🔍"}
    print(f"\n{C.BOLD}{C.CYAN}{mode_emoji.get(mode, '🔍')} Search ({mode}): {args.query}{C.RESET}\n")
    
    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        rrf_score = r.get("rrf_score")
        date = r.get("date", "")
        cid = r.get("conversation_id", "")
        ctype = r.get("chunk_type", "")
        source = r.get("source", "")
        text = r.get("text", "").replace("\n", " ")[:120]
        speakers = r.get("speakers", "[]")
        
        if isinstance(speakers, str):
            try:
                speakers = json.loads(speakers)
            except Exception:
                speakers = []
        spk_str = ", ".join(speakers) if speakers else ""

        # Show appropriate score
        display_score = rrf_score if rrf_score is not None else score
        score_color = C.GREEN if display_score > 0.1 else C.YELLOW if display_score > 0.05 else C.DIM
        
        source_indicator = f" {C.DIM}({source}){C.RESET}" if source and mode == "hybrid" else ""
        print(f"  {C.BOLD}{i}.{C.RESET} {score_color}[{display_score:.3f}]{C.RESET} {C.DIM}{date}{C.RESET} {C.DIM}({ctype}){C.RESET}{source_indicator}")
        if spk_str:
            print(f"     {C.DIM}Speakers: {spk_str}{C.RESET}")
        print(f"     {text}")
        print()


def cmd_config(args):
    """Show or edit config."""
    from src.database import PerceptDB
    db = PerceptDB()

    if args.action == "set" and args.config_args:
        if len(args.config_args) < 2:
            print(f"{C.RED}Usage: percept config set <key> <value>{C.RESET}")
            db.close()
            return
        key, value = args.config_args[0], " ".join(args.config_args[1:])
        # Store in DB settings
        db.set_setting(key, value)
        # Mask secrets in output
        display_val = value[:4] + "***" if "secret" in key.lower() else value
        print(f"{C.GREEN}✓{C.RESET} Set {C.BOLD}{key}{C.RESET} = {display_val}")
        db.close()
        return
    elif args.action == "get" and args.config_args:
        key = args.config_args[0]
        val = db.get_setting(key)
        if val is not None:
            display_val = val[:4] + "***" if "secret" in key.lower() else val
            print(f"{C.BOLD}{key}{C.RESET} = {display_val}")
        else:
            print(f"{C.DIM}{key} not set{C.RESET}")
        db.close()
        return

    # Also support legacy --set key=value
    cfg = load_config()
    if args.legacy_set:
        key, _, value = args.legacy_set.partition("=")
        if not value:
            print(f"{C.RED}Usage: --set key=value{C.RESET}")
            db.close()
            return
        parts = key.split(".")
        obj = cfg
        for p in parts[:-1]:
            obj = obj.setdefault(p, {})
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
        db.close()
        return

    # Show all config
    print(f"\n{C.BOLD}{C.CYAN}⚙ Configuration{C.RESET}\n")
    print(f"  {C.DIM}File: {CONFIG_FILE}{C.RESET}\n")
    print(json.dumps(cfg, indent=2))

    # Also show DB settings
    settings = db.get_all_settings()
    if settings:
        print(f"\n  {C.BOLD}DB Settings:{C.RESET}")
        for k, v in sorted(settings.items()):
            display_v = v[:4] + "***" if "secret" in k.lower() else v
            print(f"    {k} = {display_v}")
    print()
    db.close()


def cmd_speakers(args):
    """Manage authorized speakers."""
    from src.database import PerceptDB
    db = PerceptDB()

    if args.action == "authorize":
        if not args.speaker_id:
            print(f"{C.RED}Usage: percept speakers authorize <speaker_id>{C.RESET}")
            db.close()
            return
        speaker_id = args.speaker_id
        # Check if speaker exists in speakers table
        speakers = db.get_speakers()
        known = {s["id"] for s in speakers}
        if speaker_id not in known:
            print(f"{C.YELLOW}⚠{C.RESET}  Speaker '{speaker_id}' not in speakers table (will still be authorized)")
        db.authorize_speaker(speaker_id)
        name = next((s["name"] for s in speakers if s["id"] == speaker_id), speaker_id)
        print(f"{C.GREEN}✓{C.RESET} Authorized speaker: {C.BOLD}{speaker_id}{C.RESET} ({name})")

    elif args.action == "revoke":
        if not args.speaker_id:
            print(f"{C.RED}Usage: percept speakers revoke <speaker_id>{C.RESET}")
            db.close()
            return
        if db.revoke_speaker(args.speaker_id):
            print(f"{C.GREEN}✓{C.RESET} Revoked speaker: {C.BOLD}{args.speaker_id}{C.RESET}")
        else:
            print(f"{C.YELLOW}⚠{C.RESET}  Speaker '{args.speaker_id}' was not in authorized list")

    elif args.action == "list":
        authorized = db.get_authorized_speakers()
        if not authorized:
            print(f"\n{C.BOLD}{C.CYAN}🔐 Authorized Speakers{C.RESET}\n")
            print(f"  {C.DIM}No authorized speakers configured (all speakers allowed){C.RESET}")
            print(f"  {C.DIM}Use 'percept speakers authorize <speaker_id>' to enable allowlist{C.RESET}\n")
        else:
            print(f"\n{C.BOLD}{C.CYAN}🔐 Authorized Speakers ({len(authorized)}){C.RESET}\n")
            for s in authorized:
                name = s.get("name") or "Unknown"
                sid = s["speaker_id"]
                words = s.get("total_words") or 0
                print(f"  {C.GREEN}●{C.RESET} {C.BOLD}{sid}{C.RESET}  ({name})  {C.DIM}{words} words{C.RESET}")
            print()

        # Also show all known speakers for reference
        all_speakers = db.get_speakers()
        if all_speakers:
            auth_ids = {s["speaker_id"] for s in authorized}
            print(f"  {C.BOLD}All known speakers:{C.RESET}")
            for s in all_speakers:
                marker = f"{C.GREEN}✓{C.RESET}" if s["id"] in auth_ids else f"{C.DIM}○{C.RESET}"
                name = s.get("name") or "Unknown"
                print(f"    {marker} {s['id']}  ({name})  {s.get('total_words', 0)} words")
            print()

    else:
        print(f"{C.RED}Unknown action: {args.action}{C.RESET}")
        print(f"Usage: percept speakers <authorize|revoke|list> [speaker_id]")

    db.close()


def cmd_security_log(args):
    """Show security log."""
    from src.database import PerceptDB
    db = PerceptDB()
    events = db.get_security_log(limit=args.limit, reason=args.reason)
    db.close()

    if not events:
        print(f"\n{C.BOLD}{C.CYAN}🛡️  Security Log{C.RESET}\n")
        print(f"  {C.DIM}No security events recorded.{C.RESET}\n")
        return

    print(f"\n{C.BOLD}{C.CYAN}🛡️  Security Log ({len(events)} events){C.RESET}\n")
    for e in events:
        from datetime import datetime as _dt
        ts = _dt.fromtimestamp(e["timestamp"]).strftime("%Y-%m-%d %H:%M:%S") if e.get("timestamp") else "?"
        reason = e.get("reason", "?")
        color = {
            "unauthorized_speaker": C.RED,
            "invalid_webhook_auth": C.MAGENTA,
            "injection_detected": C.YELLOW,
        }.get(reason, C.DIM)
        snippet = (e.get("transcript_snippet") or "")[:80]
        print(f"  {color}●{C.RESET} {C.DIM}{ts}{C.RESET}  {color}{reason}{C.RESET}  speaker={e.get('speaker_id', '?')}")
        if snippet:
            print(f"    {C.DIM}\"{snippet}\"{C.RESET}")
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


def cmd_commitments(args):
    """Track commitments and promises from conversations."""
    from src.database import PerceptDB
    from src.commitment_tracker import CommitmentTracker
    from datetime import datetime

    db = PerceptDB()
    tracker = CommitmentTracker(db=db)

    action = args.action or "list"

    if action == "fulfill":
        cid = args.id
        if not cid:
            print(f"{C.RED}✗{C.RESET} --id required for fulfill")
            return
        if tracker.fulfill(cid):
            print(f"{C.GREEN}✓{C.RESET} Marked as fulfilled: {cid[:8]}...")
        else:
            print(f"{C.RED}✗{C.RESET} Failed to fulfill {cid[:8]}...")
        db.close()
        return

    if action == "cancel":
        cid = args.id
        if not cid:
            print(f"{C.RED}✗{C.RESET} --id required for cancel")
            return
        if tracker.cancel(cid):
            print(f"{C.GREEN}✓{C.RESET} Cancelled: {cid[:8]}...")
        else:
            print(f"{C.RED}✗{C.RESET} Failed to cancel {cid[:8]}...")
        db.close()
        return

    if action == "overdue":
        overdue = tracker.check_overdue()
        if not overdue:
            print(f"\n{C.GREEN}✓{C.RESET} No overdue commitments!\n")
            db.close()
            return
        print(f"\n{C.BOLD}{C.RED}⚠ Overdue Commitments{C.RESET}\n")
        for c in overdue:
            days = c["days_overdue"]
            print(f"  {C.RED}●{C.RESET} {C.BOLD}{c['speaker']}{C.RESET}: {c['action'][:80]}")
            print(f"    Due: {c['deadline']} ({days:.0f} days overdue) | Confidence: {c['confidence']:.0%}")
            print(f"    ID: {c['id'][:8]}...")
            print()
        db.close()
        return

    # Default: list open commitments
    commitments = tracker.get_open_commitments(speaker=args.speaker)
    if not commitments:
        print(f"\n{C.DIM}No open commitments.{C.RESET}\n")
        db.close()
        return

    print(f"\n{C.BOLD}{C.CYAN}📋 Open Commitments{C.RESET}\n")
    for c in commitments:
        deadline_str = f" | Due: {c['deadline']}" if c.get("deadline") else ""
        status_color = C.YELLOW if c.get("deadline_dt") and c["deadline_dt"] < datetime.now().timestamp() else C.GREEN
        extracted = datetime.fromtimestamp(c["extracted_at"]).strftime("%b %d") if c.get("extracted_at") else ""

        print(f"  {status_color}●{C.RESET} {C.BOLD}{c['speaker']}{C.RESET}: {c['action'][:80]}")
        print(f"    {extracted}{deadline_str} | Confidence: {c['confidence']:.0%} | ID: {c['id'][:8]}...")
        print()

    db.close()


def cmd_reindex(args):
    """Re-embed all conversations into vector store."""
    from src.vector_store import PerceptVectorStore
    from src.database import PerceptDB
    
    print(f"\n{C.BOLD}{C.CYAN}🔄 Reindexing Conversations{C.RESET}\n")
    
    vs = PerceptVectorStore()
    db = PerceptDB()
    
    # Show current embedder status
    embedder_type = "NVIDIA NIM" if vs._use_nvidia else "Local (sentence-transformers)"
    print(f"  Using: {C.BOLD}{embedder_type}{C.RESET}")
    print(f"  Model: {vs._model if vs._use_nvidia else vs._local_embedder.model_name}")
    print(f"  Dimensions: {vs._embedding_dim}")
    print()
    
    # Check if force rebuild needed
    existing_stats = vs.stats()
    if existing_stats["total_conversations"] > 0 and not args.force:
        print(f"  Found {existing_stats['total_conversations']} indexed conversations")
        print(f"  Use --force to rebuild the entire index")
        print()
    
    # Perform bulk indexing
    start_time = time.time()
    try:
        results = vs.index_all(db=db)
        elapsed = time.time() - start_time
        
        print(f"  {C.GREEN}✓{C.RESET} Reindexing complete in {elapsed:.1f}s")
        print(f"  Total conversations: {results['total']}")
        print(f"  Newly indexed: {results['indexed']}")
        print(f"  Skipped (already indexed): {results['skipped']}")
        if results['failed'] > 0:
            print(f"  {C.RED}Failed: {results['failed']}{C.RESET}")
            
        # Show final stats
        final_stats = vs.stats()
        print(f"\n  Final index: {final_stats['total_chunks']} chunks, {final_stats['total_conversations']} conversations")
        
    except Exception as e:
        print(f"  {C.RED}✗{C.RESET} Reindexing failed: {e}")
    finally:
        db.close()
    
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


# ── Meeting Source Connectors ──────────────────────────────────────────

def cmd_granola_sync(args):
    """Import meetings from Granola."""
    sys.path.insert(0, str(BASE_DIR))
    from tools.granola_import import main as granola_main
    # Build argv for granola_import
    argv = []
    if args.api:
        argv.append("--api")
    if args.since:
        argv.extend(["--since", args.since])
    if args.dry_run:
        argv.append("--dry-run")
    sys.argv = ["granola_import"] + argv
    granola_main()


def cmd_zoom_sync(args):
    """Sync recent Zoom cloud recordings."""
    from src.zoom_connector import sync_recent
    results = sync_recent(days=args.days)
    if not results:
        print(f"{C.DIM}No recordings with transcripts found in last {args.days} days{C.RESET}")
        return
    for r in results:
        status = r.get("status", "error")
        topic = r.get("topic", "Unknown")
        words = r.get("word_count", 0)
        icon = f"{C.GREEN}✓{C.RESET}" if status == "imported" else f"{C.RED}✗{C.RESET}"
        print(f"  {icon} {topic} ({words} words)")
    print(f"\n{C.GREEN}Imported {len([r for r in results if r.get('status') == 'imported'])} recordings{C.RESET}")


def cmd_zoom_import(args):
    """Import a specific Zoom recording or VTT file."""
    from src.zoom_connector import import_recording, import_vtt_file
    source = args.source
    if Path(source).exists():
        result = import_vtt_file(source, topic=args.topic)
    else:
        result = import_recording(source)
    if result.get("error"):
        print(f"{C.RED}✗{C.RESET} {result['error']}")
    else:
        print(f"{C.GREEN}✓{C.RESET} Imported: {result.get('topic', 'Unknown')} "
              f"({result.get('word_count', 0)} words, {result.get('segments', 0)} segments)")


def cmd_chatgpt_api(args):
    """Start ChatGPT Actions API server."""
    if args.export_schema:
        from src.chatgpt_actions import export_openapi_schema
        export_openapi_schema(args.export_schema)
        print(f"{C.GREEN}✓{C.RESET} Schema exported to {args.export_schema}")
        return
    import uvicorn
    from src.chatgpt_actions import app
    print(f"{C.GREEN}▶{C.RESET} ChatGPT Actions API on http://{args.host}:{args.port}")
    print(f"  OpenAPI schema: http://{args.host}:{args.port}/openapi.json")
    uvicorn.run(app, host=args.host, port=args.port)


# ── Main ───────────────────────────────────────────────────────────────

def main():
    """Main entry point for the Percept CLI."""
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
    p_search = sub.add_parser("search", help="Search over conversations")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--date", default=None, help="Filter by date (YYYY-MM-DD)")
    p_search.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="hybrid", 
                          help="Search mode: keyword (FTS5), semantic (vector), or hybrid (default)")

    # reindex
    p_reindex = sub.add_parser("reindex", help="Re-embed all conversations into vector store")
    p_reindex.add_argument("--force", action="store_true", help="Force rebuild entire index")

    # config
    p_cfg = sub.add_parser("config", help="Show/edit configuration")
    p_cfg.add_argument("action", nargs="?", default=None, choices=["set", "get"], help="set/get a DB setting")
    p_cfg.add_argument("config_args", nargs="*", default=[], help="key [value]")
    p_cfg.add_argument("--set", default=None, metavar="KEY=VALUE", dest="legacy_set")
    p_cfg.add_argument("--show", action="store_true")

    # speakers
    p_spk = sub.add_parser("speakers", help="Manage authorized speakers")
    p_spk.add_argument("action", choices=["authorize", "revoke", "list"], help="Action")
    p_spk.add_argument("speaker_id", nargs="?", default=None, help="Speaker ID (e.g. SPEAKER_00)")

    # security-log
    p_sec = sub.add_parser("security-log", help="Show security event log")
    p_sec.add_argument("--limit", type=int, default=50)
    p_sec.add_argument("--reason", default=None, choices=["unauthorized_speaker", "invalid_webhook_auth", "injection_detected"])

    # audit
    sub.add_parser("audit", help="Show data stats (conversations, utterances, speakers, etc.)")

    # commitments (CIL Level 2)
    p_commit = sub.add_parser("commitments", help="Track commitments and promises from conversations")
    p_commit.add_argument("action", nargs="?", default="list", choices=["list", "overdue", "fulfill", "cancel"],
                          help="list (default), overdue, fulfill <id>, cancel <id>")
    p_commit.add_argument("--speaker", default=None, help="Filter by speaker name")
    p_commit.add_argument("--id", default=None, help="Commitment ID (for fulfill/cancel)")

    # mcp
    sub.add_parser("mcp", help="Start MCP server (Model Context Protocol) for Claude Desktop")

    # purge
    p_purge = sub.add_parser("purge", help="Purge data")
    p_purge.add_argument("--older-than", type=int, default=None, metavar="DAYS", help="Delete conversations older than N days")
    p_purge.add_argument("--conversation", default=None, metavar="ID", help="Delete a specific conversation")
    p_purge.add_argument("--all", action="store_true", help="Delete all data")
    p_purge.add_argument("--confirm", action="store_true", help="Confirm destructive action")

    # ── Meeting source connectors ──
    p_granola = sub.add_parser("granola-sync", help="Import meetings from Granola (local cache or API)")
    p_granola.add_argument("--api", action="store_true", help="Use Granola Enterprise API instead of local cache")
    p_granola.add_argument("--since", default=None, help="Only import meetings after date (YYYY-MM-DD)")
    p_granola.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")

    p_zoom_sync = sub.add_parser("zoom-sync", help="Import recent Zoom cloud recordings")
    p_zoom_sync.add_argument("--days", type=int, default=7, help="How many days back to sync (default 7)")

    p_zoom_import = sub.add_parser("zoom-import", help="Import a specific Zoom recording or VTT file")
    p_zoom_import.add_argument("source", help="Zoom meeting ID or path to .vtt file")
    p_zoom_import.add_argument("--topic", default=None, help="Meeting topic (for VTT files)")

    p_chatgpt = sub.add_parser("chatgpt-api", help="Start ChatGPT Actions API server")
    p_chatgpt.add_argument("--port", type=int, default=8901, help="Port (default 8901)")
    p_chatgpt.add_argument("--host", default="127.0.0.1", help="Bind address")
    p_chatgpt.add_argument("--export-schema", type=str, default=None, help="Export OpenAPI schema to file and exit")

    # Browser audio capture
    p_browser = sub.add_parser("capture-browser", help="Capture audio from browser tabs via Chrome CDP")
    p_browser.add_argument("subcommand", nargs="?", default="status",
                          choices=["tabs", "capture", "stop", "status", "watch"],
                          help="Sub-command (default: status)")
    p_browser.add_argument("--tab", help="Tab ID (auto-detects meeting if omitted)")
    p_browser.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="Chrome CDP URL")
    p_browser.add_argument("--interval", type=int, default=15, help="Watch check interval (seconds)")

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
        "reindex": cmd_reindex,
        "audit": cmd_audit,
        "commitments": cmd_commitments,
        "purge": cmd_purge,
        "speakers": cmd_speakers,
        "security-log": cmd_security_log,
        "mcp": lambda _: __import__("src.mcp_server", fromlist=["run"]).run(),
        "granola-sync": cmd_granola_sync,
        "zoom-sync": cmd_zoom_sync,
        "zoom-import": cmd_zoom_import,
        "chatgpt-api": cmd_chatgpt_api,
        "capture-browser": lambda a: __import__(
            "src.browser_capture.cli", fromlist=["main"]
        ).main([a.subcommand] + (["--tab", a.tab] if a.tab else []) +
               ["--cdp-url", a.cdp_url] +
               (["--interval", str(a.interval)] if a.subcommand == "watch" else [])),
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
