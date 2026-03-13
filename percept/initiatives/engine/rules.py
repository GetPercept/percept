"""Rule, Condition, Action dataclasses and YAML loader."""
from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class Condition:
    source: str                        # Connector name or "*" for any
    signal_type: str                   # Signal type or "*" for any
    operator: str = "exists"           # "exists", "gt", "lt", "eq", "contains", "and", "or"
    value: Any = None                  # Comparison value
    field: str = "value"               # Which data field to compare
    time_window_minutes: Optional[int] = None  # Look back this far

    @classmethod
    def from_dict(cls, d: dict) -> Condition:
        return cls(
            source=d.get("source", "*"),
            signal_type=d.get("signal_type", d.get("signal", "*")),
            operator=d.get("operator", "exists"),
            value=d.get("value"),
            field=d.get("field", "value"),
            time_window_minutes=d.get("time_window_minutes", d.get("time_window")),
        )


@dataclass
class Action:
    action_type: str = "notify"          # "notify", "execute", "draft", "escalate", "log"
    target: str = ""                     # Who/where
    template: str = ""                   # Message template with {variable} placeholders
    require_approval: bool = False       # Ask before executing?

    @classmethod
    def from_dict(cls, d: dict) -> Action:
        return cls(
            action_type=d.get("action_type", d.get("type", "notify")),
            target=d.get("target", ""),
            template=d.get("template", d.get("message", "")),
            require_approval=d.get("require_approval", False),
        )


@dataclass
class Rule:
    name: str
    description: str = ""
    conditions: list[Condition] = field(default_factory=list)
    action: Action = field(default_factory=Action)
    cooldown_minutes: int = 60
    priority: int = 3                    # 1 (highest) to 5 (lowest)
    enabled: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> Rule:
        conditions = [Condition.from_dict(c) for c in d.get("conditions", [])]
        action_raw = d.get("action", {})
        action = Action.from_dict(action_raw) if isinstance(action_raw, dict) else Action(template=str(action_raw))
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            conditions=conditions,
            action=action,
            cooldown_minutes=d.get("cooldown_minutes", d.get("cooldown", 60)),
            priority=d.get("priority", 3),
            enabled=d.get("enabled", True),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "conditions": [
                {
                    "source": c.source,
                    "signal_type": c.signal_type,
                    "operator": c.operator,
                    "value": c.value,
                    "field": c.field,
                    "time_window_minutes": c.time_window_minutes,
                }
                for c in self.conditions
            ],
            "action": {
                "action_type": self.action.action_type,
                "target": self.action.target,
                "template": self.action.template,
                "require_approval": self.action.require_approval,
            },
            "cooldown_minutes": self.cooldown_minutes,
            "priority": self.priority,
            "enabled": self.enabled,
        }


def load_rules_from_yaml(path: Path) -> list[Rule]:
    """Load rules from a YAML file. Supports single rule or list of rules."""
    with open(path) as f:
        data = yaml.safe_load(f)
    if data is None:
        return []
    if isinstance(data, dict):
        # Could be {"rules": [...]} or a single rule
        if "rules" in data:
            return [Rule.from_dict(r) for r in data["rules"]]
        return [Rule.from_dict(data)]
    if isinstance(data, list):
        return [Rule.from_dict(r) for r in data]
    return []


def load_all_rules(rules_dir: Path) -> list[Rule]:
    """Load all .yaml/.yml files from the rules directory."""
    rules = []
    if not rules_dir.exists():
        return rules
    for f in sorted(rules_dir.glob("*.y*ml")):
        try:
            rules.extend(load_rules_from_yaml(f))
        except Exception as e:
            print(f"Warning: Failed to load {f}: {e}")
    return rules
