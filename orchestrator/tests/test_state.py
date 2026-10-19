"""Tests for state.py — BKT update, difficulty selection, turn-history window,
and correction_cycle_count bookkeeping. Covers every row of the test_state.py
table in tutor-orchestrator-impl.md Section 10."""

from __future__ import annotations

from datetime import datetime

from orchestrator import state as state_module
from orchestrator.models import LearnerState, OrchestratorDecision, AdaptationContext, Turn


def make_state(**overrides) -> LearnerState:
    defaults = dict(
        session_id="sess_1",
        topic="math.ratio.speed_distance_time",
        language="en",
        level="medium",
        current_problem_id="prob_001",
        attempt_count=1,
        correction_cycle_count=0,
        mastery_by_skill={},
        misconceptions=[],
        hesitation_score=0.0,
        last_3_turns=[],
    )
    defaults.update(overrides)
    return LearnerState(**defaults)


def make_decision(final_strategy: str, state: LearnerState) -> OrchestratorDecision:
    return OrchestratorDecision(
        final_strategy=final_strategy,
        policy_override=False,
        response_draft=None,
        adaptation_context=AdaptationContext.from_state(state),
        soften_flag=False,
        flag_for_review=False,
        problem_id=state.current_problem_id,
        session_id=state.session_id,
    )


# --- BKT update --------------------------------------------------------------

def test_bkt_updates_upward_on_correct():
    new_p = state_module.bkt_update(p_know=0.5, is_correct=True)
    assert new_p > 0.5


def test_bkt_updates_downward_on_incorrect():
    new_p = state_module.bkt_update(p_know=0.7, is_correct=False)
    assert new_p < 0.7


def test_bkt_never_reaches_0_or_1():
    low = state_module.bkt_update(p_know=0.01, is_correct=False)
    high = state_module.bkt_update(p_know=0.99, is_correct=True)
    assert 0.01 <= low <= 0.99
    assert 0.01 <= high <= 0.99
    assert low >= 0.01
    assert high <= 0.99


# --- Difficulty selection -----------------------------------------------------

def test_difficulty_advances_at_high_mastery():
    state = make_state(
        level="easy",
        current_problem_id="prob_001",
        mastery_by_skill={"math.ratio.speed_distance_time": 0.96},
    )
    assert state_module.select_next_difficulty(state) == "medium"


def test_difficulty_retreats_at_low_mastery_after_3_attempts():
    state = make_state(
        level="medium",
        current_problem_id="prob_001",
        mastery_by_skill={"math.ratio.speed_distance_time": 0.15},
        attempt_count=3,
    )
    assert state_module.select_next_difficulty(state) == "easy"


def test_difficulty_stays_mid_range():
    state = make_state(
        level="medium",
        current_problem_id="prob_001",
        mastery_by_skill={"math.ratio.speed_distance_time": 0.5},
    )
    assert state_module.select_next_difficulty(state) == "medium"


# --- correction_cycle_count ----------------------------------------------------

def test_correction_cycle_count_resets_on_correct():
    state = make_state(correction_cycle_count=3)
    decision = make_decision("ACKNOWLEDGE", state)
    new_state = state_module.update_after_turn(state, decision, "utterance", "response")
    assert new_state.correction_cycle_count == 0


def test_correction_cycle_count_increments_otherwise():
    state = make_state(correction_cycle_count=2)
    decision = make_decision("HINT", state)
    new_state = state_module.update_after_turn(state, decision, "utterance", "response")
    assert new_state.correction_cycle_count == 3


# --- last_3_turns window --------------------------------------------------------

def test_last_3_turns_keeps_max_6_entries():
    # Seed with 8 pre-existing turns (4 pairs) to simulate a long-running session.
    seeded = [
        Turn(role="learner" if i % 2 == 0 else "tutor", text=f"turn {i}", timestamp=datetime.utcnow())
        for i in range(8)
    ]
    state = make_state(last_3_turns=seeded)
    decision = make_decision("HINT", state)
    new_state = state_module.update_after_turn(state, decision, "utterance", "response")
    assert len(new_state.last_3_turns) == 6
    # Most recent turns (the ones just appended) must be the ones retained.
    assert new_state.last_3_turns[-2].text == "utterance"
    assert new_state.last_3_turns[-1].text == "response"


def test_update_after_turn_does_not_mutate_original_state():
    state = make_state(attempt_count=1, correction_cycle_count=0)
    decision = make_decision("HINT", state)
    state_module.update_after_turn(state, decision, "utterance", "response")
    assert state.attempt_count == 1
    assert state.correction_cycle_count == 0
    assert state.last_3_turns == []
