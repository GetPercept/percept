#!/usr/bin/env python3.11
"""Initiative Engine CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from percept.initiatives.config import RULES_DIR
from percept.initiatives.engine.core import InitiativeEngine
from percept.initiatives.engine.signals import Signal, SignalBuffer
from percept.initiatives.engine.rules import load_all_rules, load_rules_from_yaml
from percept.initiatives.engine.actions import ActionHistory


def get_engine() -> InitiativeEngine:
    rules = load_all_rules(RULES_DIR)
    return InitiativeEngine(rules)


def cmd_status(args):
    engine = get_engine()
    s = engine.status()
    print("Initiative Engine Status")
    print("=" * 40)
    print(f"  Rules (total):    {s['rules_total']}")
    print(f"  Rules (enabled):  {s['rules_enabled']}")
    print(f"  Rules (disabled): {s['rules_disabled']}")
    print(f"  Signal buffer:    {s['signal_buffer_size']} signals")
    print(f"  Active cooldowns: {s['active_cooldowns']}")


def cmd_rules(args):
    if args.subcommand == "add":
        path = Path(args.yaml_file)
        if not path.exists():
            print(f"Error: {path} not found")
            sys.exit(1)
        new_rules = load_rules_from_yaml(path)
        # Copy to rules dir
        import shutil
        dest = RULES_DIR / path.name
        shutil.copy2(path, dest)
        print(f"Added {len(new_rules)} rule(s) from {path.name}:")
        for r in new_rules:
            print(f"  • {r.name} (priority {r.priority})")

    elif args.subcommand == "enable":
        engine = get_engine()
        if engine.enable_rule(args.name):
            print(f"Enabled rule: {args.name}")
        else:
            print(f"Rule not found: {args.name}")
            sys.exit(1)

    elif args.subcommand == "disable":
        engine = get_engine()
        if engine.disable_rule(args.name):
            print(f"Disabled rule: {args.name}")
        else:
            print(f"Rule not found: {args.name}")
            sys.exit(1)

    else:
        # List all rules
        rules = load_all_rules(RULES_DIR)
        if not rules:
            print("No rules loaded. Add YAML files to rules/")
            return
        print(f"{'Name':<30} {'Pri':>3} {'Enabled':<8} {'Cooldown':<10} {'Action':<10}")
        print("-" * 70)
        for r in sorted(rules, key=lambda x: x.priority):
            status = "✓" if r.enabled else "✗"
            print(f"{r.name:<30} {r.priority:>3} {status:<8} {r.cooldown_minutes}min{'':<5} {r.action.action_type:<10}")
            if r.description:
                print(f"  └─ {r.description}")


def cmd_simulate(args):
    signal_data = json.loads(args.signal_json)
    signal = Signal.from_dict(signal_data)

    engine = get_engine()
    results = engine.simulate(signal)

    print(f"Simulating signal: {signal.source}/{signal.signal_type}")
    print(f"  Entity: {signal.entity}")
    print(f"  Data: {signal.data}")
    print()

    if not results:
        print("No rules would fire.")
    else:
        print(f"{len(results)} rule(s) would fire:")
        for r in results:
            print(f"  [{r['priority']}] {r['rule']}: {r['message']}")


def cmd_history(args):
    history = ActionHistory()
    records = history.recent(limit=args.limit or 20, rule_name=args.rule)

    if not records:
        print("No action history.")
        return

    print(f"{'Time':<22} {'Rule':<25} {'Type':<10} {'Message'}")
    print("-" * 90)
    for r in records:
        ts = r["timestamp"][:19].replace("T", " ")
        msg = r["message"][:50] + "..." if len(r["message"]) > 50 else r["message"]
        print(f"{ts:<22} {r['rule_name']:<25} {r['action_type']:<10} {msg}")


def cmd_run(args):
    engine = get_engine()
    if args.daemon:
        engine.run_daemon()
    else:
        results = engine.run_once()
        if results:
            print(f"Fired {len(results)} action(s):")
            for r in results:
                print(f"  [{r['priority']}] {r['rule']}: {r['message']}")
        else:
            print("No rules fired.")


def cmd_digest(args):
    engine = get_engine()
    # Inject a time_trigger signal to fire digest rules
    from datetime import datetime, timezone
    signal = Signal(
        source="system",
        signal_type="time_trigger",
        entity="system",
        data={"value": "17:00", "trigger": "manual_digest"},
        urgency=0.3,
        confidence=1.0,
    )
    results = engine.ingest_signal(signal)
    if results:
        print(f"Digest triggered {len(results)} action(s):")
        for r in results:
            print(f"  {r['message']}")
    else:
        print("No digest rules fired. Ensure digest.yaml is configured.")


def main():
    parser = argparse.ArgumentParser(description="Initiative Engine CLI")
    sub = parser.add_subparsers(dest="command")

    # status
    sub.add_parser("status", help="Engine status")

    # rules
    rules_parser = sub.add_parser("rules", help="Manage rules")
    rules_sub = rules_parser.add_subparsers(dest="subcommand")
    add_parser = rules_sub.add_parser("add", help="Add rules from YAML")
    add_parser.add_argument("yaml_file", help="Path to YAML file")
    enable_parser = rules_sub.add_parser("enable", help="Enable a rule")
    enable_parser.add_argument("name", help="Rule name")
    disable_parser = rules_sub.add_parser("disable", help="Disable a rule")
    disable_parser.add_argument("name", help="Rule name")

    # simulate
    sim_parser = sub.add_parser("simulate", help="Simulate a signal")
    sim_parser.add_argument("signal_json", help="Signal as JSON string")

    # history
    hist_parser = sub.add_parser("history", help="View action history")
    hist_parser.add_argument("--rule", help="Filter by rule name")
    hist_parser.add_argument("--limit", type=int, help="Max records")

    # run
    run_parser = sub.add_parser("run", help="Run the engine")
    run_parser.add_argument("--once", action="store_true", help="Evaluate once and exit")
    run_parser.add_argument("--daemon", action="store_true", help="Run continuously")

    # digest
    sub.add_parser("digest", help="Generate digest now")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "rules":
        cmd_rules(args)
    elif args.command == "simulate":
        cmd_simulate(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "digest":
        cmd_digest(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
