"""InitiativeEngine — the main loop that evaluates rules against signals."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from percept.initiatives.config import ENGINE_POLL_INTERVAL_SECONDS
from percept.initiatives.engine.actions import ActionHistory, fire_action
from percept.initiatives.engine.evaluator import evaluate_rule
from percept.initiatives.engine.rules import Rule, load_all_rules
from percept.initiatives.engine.signals import Signal, SignalBuffer


class InitiativeEngine:
    def __init__(self, rules: list[Rule], buffer: Optional[SignalBuffer] = None, history: Optional[ActionHistory] = None):
        self.rules = rules
        self.signal_buffer = buffer or SignalBuffer()
        self.history = history or ActionHistory()
        self.cooldowns: dict[str, datetime] = {}  # rule_name -> last_fired

    def ingest_signal(self, signal: Signal) -> list[dict]:
        """Add a signal to the buffer and evaluate rules. Returns list of fired actions."""
        self.signal_buffer.add(signal)
        return self.evaluate_rules()

    def evaluate_rules(self) -> list[dict]:
        """Check all rules against current signal buffer. Returns fired actions."""
        fired = []
        for rule in sorted(self.rules, key=lambda r: r.priority):
            if not rule.enabled:
                continue
            if self._in_cooldown(rule):
                continue
            met, context = evaluate_rule(rule, self.signal_buffer)
            if met:
                rendered = fire_action(rule.name, rule.action, context, self.history)
                self._set_cooldown(rule)
                fired.append({
                    "rule": rule.name,
                    "action_type": rule.action.action_type,
                    "message": rendered,
                    "priority": rule.priority,
                })
        return fired

    def simulate(self, signal: Signal) -> list[dict]:
        """Simulate ingesting a signal without persisting. Returns what would fire."""
        self.signal_buffer.add(signal)
        fired = []
        for rule in sorted(self.rules, key=lambda r: r.priority):
            if not rule.enabled:
                continue
            met, context = evaluate_rule(rule, self.signal_buffer)
            if met and not self._in_cooldown(rule):
                from percept.initiatives.engine.actions import render_template
                rendered = render_template(rule.action.template, context)
                fired.append({
                    "rule": rule.name,
                    "action_type": rule.action.action_type,
                    "message": rendered,
                    "priority": rule.priority,
                    "simulated": True,
                })
        return fired

    def _in_cooldown(self, rule: Rule) -> bool:
        last_fired = self.cooldowns.get(rule.name)
        if last_fired is None:
            return False
        elapsed = (datetime.now(timezone.utc) - last_fired).total_seconds() / 60
        return elapsed < rule.cooldown_minutes

    def _set_cooldown(self, rule: Rule):
        self.cooldowns[rule.name] = datetime.now(timezone.utc)

    def get_rule(self, name: str) -> Optional[Rule]:
        for rule in self.rules:
            if rule.name == name:
                return rule
        return None

    def enable_rule(self, name: str) -> bool:
        rule = self.get_rule(name)
        if rule:
            rule.enabled = True
            return True
        return False

    def disable_rule(self, name: str) -> bool:
        rule = self.get_rule(name)
        if rule:
            rule.enabled = False
            return True
        return False

    def status(self) -> dict:
        return {
            "rules_total": len(self.rules),
            "rules_enabled": sum(1 for r in self.rules if r.enabled),
            "rules_disabled": sum(1 for r in self.rules if not r.enabled),
            "signal_buffer_size": self.signal_buffer.count(),
            "active_cooldowns": sum(1 for r in self.rules if self._in_cooldown(r)),
        }

    def run_once(self) -> list[dict]:
        """Evaluate all rules once and return results."""
        return self.evaluate_rules()

    def run_daemon(self, poll_interval: int = ENGINE_POLL_INTERVAL_SECONDS):
        """Run continuously, evaluating rules on each cycle."""
        print(f"Initiative Engine started (polling every {poll_interval}s)")
        print(f"  {len(self.rules)} rules loaded, {sum(1 for r in self.rules if r.enabled)} enabled")
        try:
            while True:
                fired = self.evaluate_rules()
                if fired:
                    print(f"  [{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Fired {len(fired)} action(s)")
                self.signal_buffer.prune()
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\nEngine stopped.")
