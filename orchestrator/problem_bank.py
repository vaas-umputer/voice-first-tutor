"""Loads and queries problems.json. See section 3 of the impl spec."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List

from .models import Problem

_BANK: Dict[str, Problem] = {}


def load() -> None:
    """Call once at application startup."""
    path = Path(__file__).parent / "problems.json"
    data = json.loads(path.read_text())
    for entry in data:
        p = Problem(**entry)
        _BANK[p.id] = p


def get(problem_id: str) -> Problem:
    if not _BANK:
        load()
    return _BANK[problem_id]


def select_for_level(level: str, exclude_ids: List[str] = None) -> Problem:
    """Return a random problem at the given difficulty, excluding already-seen ones."""
    if not _BANK:
        load()
    exclude_ids = exclude_ids or []
    candidates = [
        p for p in _BANK.values()
        if p.difficulty == level and p.id not in exclude_ids
    ]
    if not candidates:
        # All problems at this level exhausted - wrap around
        candidates = [p for p in _BANK.values() if p.difficulty == level]
    return random.choice(candidates)
