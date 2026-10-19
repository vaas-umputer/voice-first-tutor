"""Tests for policy.py — constraint pipeline. Covers every row of the
test_policy.py table in tutor-orchestrator-impl.md Section 10."""

from __future__ import annotations

from orchestrator import policy
from orchestrator.models import LearnerState, LLMReasoningOutput


def make_state(**overrides) -> LearnerState:
    """Minimal LearnerState with sane defaults, overridable per test."""
    defaults = dict(
        session_id="sess_1",
        topic="math.ratio.speed_distance_time",
        language="en",
        level="easy",
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


def make_output(**overrides) -> LLMReasoningOutput:
    defaults = dict(
        classification="CORRECT",
        strategy="ACKNOWLEDGE",
        reasoning="test reasoning",
        response="Great job, want another?",
    )
    defaults.update(overrides)
    return LLMReasoningOutput(**defaults)


def test_correction_blocked_on_attempt_1():
    output = make_output(classification="MISCONCEPTION", strategy="CORRECTION")
    state = make_state(attempt_count=1)
    decision = policy.enforce(output, state)
    assert decision.final_strategy == "COUNTEREXAMPLE"
    assert decision.policy_override is True


def test_correction_allowed_on_attempt_2():
    output = make_output(classification="MISCONCEPTION", strategy="CORRECTION")
    state = make_state(attempt_count=2)
    decision = policy.enforce(output, state)
    assert decision.final_strategy == "CORRECTION"
    assert decision.policy_override is False


def test_next_problem_blocked_on_wrong_classification():
    output = make_output(classification="STUCK", strategy="NEXT_PROBLEM")
    state = make_state(attempt_count=1)
    decision = policy.enforce(output, state)
    assert decision.final_strategy == "HINT"
    assert decision.policy_override is True


def test_hesitation_softens_probe():
    output = make_output(classification="PARTIALLY_CORRECT", strategy="PROBE")
    state = make_state(hesitation_score=0.8)
    decision = policy.enforce(output, state)
    assert decision.final_strategy == "HINT"
    assert decision.policy_override is True
    assert decision.soften_flag is True


def test_hesitation_does_not_fire_below_threshold():
    output = make_output(classification="PARTIALLY_CORRECT", strategy="PROBE")
    state = make_state(hesitation_score=0.4)
    decision = policy.enforce(output, state)
    assert decision.final_strategy == "PROBE"
    assert decision.policy_override is False


def test_stuck_escalates_at_attempt_3():
    output = make_output(classification="STUCK", strategy="HINT")
    state = make_state(attempt_count=3)
    decision = policy.enforce(output, state)
    assert decision.final_strategy == "SIMPLER_SUBPROBLEM"
    assert decision.policy_override is True


def test_stuck_does_not_escalate_at_attempt_2():
    output = make_output(classification="STUCK", strategy="HINT")
    state = make_state(attempt_count=2)
    decision = policy.enforce(output, state)
    assert decision.final_strategy == "HINT"
    assert decision.policy_override is False


def test_challenge_blocked_below_mastery():
    output = make_output(classification="CHALLENGE_READY", strategy="CHALLENGE")
    state = make_state(
        current_problem_id="prob_001",
        mastery_by_skill={"math.ratio.speed_distance_time": 0.7},
    )
    decision = policy.enforce(output, state)
    assert decision.final_strategy == "PROBE"
    assert decision.policy_override is True


def test_challenge_allowed_at_or_above_mastery():
    output = make_output(classification="CHALLENGE_READY", strategy="CHALLENGE")
    state = make_state(
        current_problem_id="prob_001",
        mastery_by_skill={"math.ratio.speed_distance_time": 0.87},
    )
    decision = policy.enforce(output, state)
    assert decision.final_strategy == "CHALLENGE"
    assert decision.policy_override is False


def test_off_topic_hard_override():
    output = make_output(classification="OFF_TOPIC", strategy="PROBE")
    state = make_state()
    decision = policy.enforce(output, state)
    assert decision.final_strategy == "REDIRECT"
    assert decision.policy_override is True
    assert decision.response_draft is None


def test_correction_cycle_limit_fires_at_5():
    output = make_output(classification="PARTIALLY_CORRECT", strategy="PROBE")
    state = make_state(correction_cycle_count=5)
    decision = policy.enforce(output, state)
    assert decision.final_strategy == "SIMPLER_SUBPROBLEM"
    assert decision.policy_override is True
    assert decision.flag_for_review is True


def test_parse_failure_fallback():
    state = make_state(attempt_count=1)
    decision = policy.enforce(None, state)
    assert decision.final_strategy == "HINT"
    assert decision.policy_override is True


def test_parse_failure_escalates():
    state = make_state(attempt_count=4)
    decision = policy.enforce(None, state)
    assert decision.final_strategy == "SIMPLER_SUBPROBLEM"
    assert decision.policy_override is True
