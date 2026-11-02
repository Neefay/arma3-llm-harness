"""Event matchers: small, JSON-friendly predicates usable from MCP tools and scenario files.

A match spec is a dict of field -> condition. A condition is either a plain value (equality) or an
operator dict: {"$in": [...]}, {"$contains": x}, {"$re": "pattern"}, {"$exists": bool},
{"$gt": n}, {"$gte": n}, {"$lt": n}, {"$lte": n}, {"$ne": v}.
Dotted keys reach into nested objects: {"value.0.ROUND_WINNER": "DRAW"}.
"""
from __future__ import annotations

import re
from typing import Any

_MISSING = object()


def get_path(obj: Any, dotted: str) -> Any:
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part, _MISSING)
        elif isinstance(cur, list) and part.lstrip("-").isdigit():
            idx = int(part)
            cur = cur[idx] if -len(cur) <= idx < len(cur) else _MISSING
        else:
            return _MISSING
        if cur is _MISSING:
            return _MISSING
    return cur


def _check(value: Any, cond: Any) -> bool:
    if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
        for op, arg in cond.items():
            if op == "$exists":
                if (value is not _MISSING) != bool(arg):
                    return False
                continue
            if value is _MISSING:
                return False
            if op == "$in" and value not in arg:
                return False
            if op == "$ne" and value == arg:
                return False
            if op == "$contains":
                if isinstance(value, str | list | dict):
                    if arg not in value:
                        return False
                else:
                    return False
            if op == "$re" and not (isinstance(value, str) and re.search(arg, value)):
                return False
            if op in ("$gt", "$gte", "$lt", "$lte"):
                if not isinstance(value, int | float):
                    return False
                if op == "$gt" and not value > arg:
                    return False
                if op == "$gte" and not value >= arg:
                    return False
                if op == "$lt" and not value < arg:
                    return False
                if op == "$lte" and not value <= arg:
                    return False
            if op not in ("$exists", "$in", "$ne", "$contains", "$re", "$gt", "$gte", "$lt", "$lte"):
                raise ValueError(f"unknown match operator {op}")
        return True
    return value is not _MISSING and value == cond


def matches(event: dict, spec: dict) -> bool:
    return all(_check(get_path(event, k), cond) for k, cond in spec.items())


OPERATORS = {"$exists", "$in", "$ne", "$contains", "$re", "$gt", "$gte", "$lt", "$lte"}


def validate(spec: dict) -> None:
    if not isinstance(spec, dict) or not spec:
        raise ValueError("match spec must be a non-empty object, e.g. {\"k\": \"evt\", \"type\": \"fsm\"}")
    for key, cond in spec.items():
        if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
            unknown = set(cond) - OPERATORS
            if unknown:
                raise ValueError(f"{key}: unknown operator(s) {sorted(unknown)}; known: {sorted(OPERATORS)}")


def matcher(spec: dict):
    validate(spec)
    return lambda e: matches(e, spec)
