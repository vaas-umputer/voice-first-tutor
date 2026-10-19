"""LearnerState struct updates, BKT, difficulty selection, SQLite persistence.
See section 6 of the impl spec."""

from __future__ import annotations

import copy
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import problem_bank
from .models import LearnerState, OrchestratorDecision, Turn

DB_PATH = Path(__file__).parent / "tutor_sessions.db"

# BKT parameters - fixed for MVP; will be per-skill in Phase 2
P_TRANSIT = 0.10  # P(learn | not known) per attempt
P_SLIP = 0.10  # P(wrong | known)
P_GUESS = 0.20  # P(right | not known)

MASTERY_ADVANCE_THRESHOLD = 0.95  # advance to harder difficulty
MASTERY_RETREAT_THRESHOLD = 0.20  # retreat to easier difficulty (after 3 attempts)
RETREAT_ATTEMPT_MINIMUM = 3


def update_after_turn(
    state: LearnerState,
    decision: OrchestratorDecision,
    utterance: str,
    tutor_response: str,
) -> LearnerState:
    """Return a new LearnerState. Do not mutate the original."""
    s = copy.deepcopy(state)

    # 1. Append to rolling turn history
    s.last_3_turns.append(Turn(role="learner", text=utterance, timestamp=datetime.utcnow()))
    s.last_3_turns.append(Turn(role="tutor", text=tutor_response, timestamp=datetime.utcnow()))
    s.last_3_turns = s.last_3_turns[-6:]  # keep last 3 tutor+learner pairs = 6 turns

    # 2. Update attempt count
    s.attempt_count += 1

    # 3. Update correction cycle counter
    if decision.final_strategy in ("ACKNOWLEDGE", "NEXT_PROBLEM", "CHALLENGE"):
        s.correction_cycle_count = 0
    else:
        s.correction_cycle_count += 1

    # 4. BKT mastery update
    problem = problem_bank.get(state.current_problem_id)
    is_correct = decision.final_strategy in ("ACKNOWLEDGE", "NEXT_PROBLEM", "CHALLENGE")
    current_mastery = s.mastery_by_skill.get(problem.skill_code, 0.3)
    s.mastery_by_skill[problem.skill_code] = bkt_update(
        p_know=current_mastery,
        is_correct=is_correct,
    )

    return s


def bkt_update(p_know: float, is_correct: bool) -> float:
    """
    Update P(Learned) after observing a correct or incorrect response.
    Returns the new p_know (clamped to [0.01, 0.99]).
    """
    if is_correct:
        p_obs_given_know = 1.0 - P_SLIP
        p_obs_given_not = P_GUESS
    else:
        p_obs_given_know = P_SLIP
        p_obs_given_not = 1.0 - P_GUESS

    # Posterior via Bayes
    numerator = p_obs_given_know * p_know
    denominator = numerator + p_obs_given_not * (1.0 - p_know)
    p_know_posterior = numerator / denominator

    # Apply learning transition
    p_know_new = p_know_posterior + (1.0 - p_know_posterior) * P_TRANSIT

    return max(0.01, min(0.99, p_know_new))


def select_next_difficulty(state: LearnerState) -> str:
    problem = problem_bank.get(state.current_problem_id)
    mastery = state.mastery_by_skill.get(problem.skill_code, 0.3)

    if mastery >= MASTERY_ADVANCE_THRESHOLD:
        return _advance_level(state.level)

    if mastery < MASTERY_RETREAT_THRESHOLD and state.attempt_count >= RETREAT_ATTEMPT_MINIMUM:
        return _retreat_level(state.level)

    return state.level  # stay


def _advance_level(level: str) -> str:
    return {"easy": "medium", "medium": "hard", "hard": "hard"}[level]


def _retreat_level(level: str) -> str:
    return {"easy": "easy", "medium": "easy", "hard": "medium"}[level]


def init_db() -> None:
    """Call once at application startup."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS learner_states (
            session_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def flush_state(state: LearnerState) -> None:
    """Write current state to SQLite. Called on turn end, not hot path critical."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO learner_states (session_id, state_json, updated_at)
        VALUES (?, ?, datetime('now'))
    """, (state.session_id, json.dumps(asdict(state), default=str)))
    conn.commit()
    conn.close()
