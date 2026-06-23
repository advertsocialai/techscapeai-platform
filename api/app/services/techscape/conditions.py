"""
Tiny safe condition evaluator for `condition_logic` in workflow_steps.

Schema:
  {"op": "and|or", "rules": [<rule>, ...]}
  {"op": "==|!=|>|>=|<|<=|in|contains|truthy|falsy",
   "left":  "<dotted.path>",
   "right": <value>}

Paths support dotted lookups against the execution context, e.g.
  "trigger_data.payment_status"  → ctx["trigger_data"]["payment_status"]
  "client.email"                 → ctx["client"]["email"]

Returns False on missing paths to keep workflows safe.
Designed to refuse anything outside this schema (no eval()).
"""
from __future__ import annotations
from typing import Any, Mapping


_BIN_OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">":  lambda a, b: _cmp(a, b) > 0,
    ">=": lambda a, b: _cmp(a, b) >= 0,
    "<":  lambda a, b: _cmp(a, b) < 0,
    "<=": lambda a, b: _cmp(a, b) <= 0,
    "in": lambda a, b: isinstance(b, (list, tuple, set, str)) and a in b,
    "contains": lambda a, b: isinstance(a, (list, tuple, set, str, dict)) and b in a,
}
_UNARY = {"truthy", "falsy"}


def _cmp(a: Any, b: Any) -> int:
    try:
        if a == b:
            return 0
        return 1 if a > b else -1
    except TypeError:
        return 0


def resolve(path: str, ctx: Mapping[str, Any]) -> Any:
    cur: Any = ctx
    for part in (path or "").split("."):
        if part == "":
            return cur
        if isinstance(cur, Mapping):
            cur = cur.get(part)
        else:
            return None
    return cur


def evaluate(rule: Any, ctx: Mapping[str, Any]) -> bool:
    if rule is None:
        return True
    if not isinstance(rule, Mapping):
        return False

    op = rule.get("op")
    if op in ("and", "or"):
        rules = rule.get("rules") or []
        if not isinstance(rules, list):
            return False
        if op == "and":
            return all(evaluate(r, ctx) for r in rules)
        return any(evaluate(r, ctx) for r in rules)

    left_path = rule.get("left")
    if left_path is None:
        return False
    left = resolve(left_path, ctx)

    if op in _UNARY:
        return bool(left) if op == "truthy" else not bool(left)

    if op in _BIN_OPS:
        return _BIN_OPS[op](left, rule.get("right"))

    return False
