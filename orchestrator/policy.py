"""Constraint pipeline. Pure Python, no I/O, no async. See section 5 of the impl spec."""

from __future__ import annotations

from typing import Optional, Tuple

from . import problem_bank
from .models import AdaptationContext, LearnerState, LLMReasoningOutput, OrchestratorDecision

VALID_CLASSIFICATIONS = {
    "CORRECT", "PARTIALLY_CORRECT", "MISCONCEPTION",
    "STUCK", "CHALLENGE_READY", "OFF_TOPIC",
}
VALID_STRATEGIES = {
    "ACKNOWLEDGE", "PROBE", "HINT", "COUNTEREXAMPLE",
    "CORRECTION", "SIMPLER_SUBPROBLEM", "CHALLENGE",
    "REDIRECT", "NEXT_PROBLEM",
}

CHALLENGE_MASTERY_THRESHOLD = 0.85
CORRECTION_CYCLE_LIMIT = 5

SOFTEN_MAP = {
    "PROBE": "HINT",
    "CHALLENGE": "PROBE",
    "CORRECTION": "HINT",
}


# --- Stage 1: validate ------------------------------------------------------

def rule_validate_output(
    output: Optional[LLMReasoningOutput],
    state: LearnerState,
) -> Tuple[LLMReasoningOutput, bool]:
    if output is None:
        return _fallback(state, "parse_failure"), True

    if output.classification not in VALID_CLASSIFICATIONS:
        return _fallback(state, "invalid_classification"), True

    if output.strategy not in VALID_STRATEGIES:
        return _fallback(state, "invalid_strategy"), True

    if output.response and len(output.response.split()) > 40:
        output.response = _trim_to_sentence(output.response)

    return output, False


def _fallback(state: LearnerState, reason: str) -> LLMReasoningOutput:
    strategy = "HINT" if state.attempt_count <= 2 else "SIMPLER_SUBPROBLEM"
    return LLMReasoningOutput(
        classification="STUCK",
        strategy=strategy,
        reasoning="policy_fallback:{}".format(reason),
        response=None,
    )


def _trim_to_sentence(text: str) -> str:
    """Return text up to and including the first sentence boundary."""
    for i, ch in enumerate(text):
        if ch in ".?!" and i < len(text) - 1:
            return text[: i + 1]
    return text  # no boundary found - return as-is


# --- Stage 2: constraint rules ----------------------------------------------

def rule_no_correction_on_first(
    output: LLMReasoningOutput, state: LearnerState
) -> Tuple[LLMReasoningOutput, bool]:
    if output.strategy == "CORRECTION" and state.attempt_count <= 1:
        output.strategy = "COUNTEREXAMPLE"
        return output, True
    return output, False


def rule_no_direct_answer(
    output: LLMReasoningOutput, state: LearnerState
) -> Tuple[LLMReasoningOutput, bool]:
    if (
        output.strategy == "NEXT_PROBLEM"
        and output.classification not in ("CORRECT", "CHALLENGE_READY")
    ):
        output.strategy = "HINT"
        return output, True
    return output, False


def rule_hesitation_softening(
    output: LLMReasoningOutput, state: LearnerState
) -> Tuple[LLMReasoningOutput, bool]:
    if state.hesitation_score < 0.6:
        return output, False

    if output.strategy in SOFTEN_MAP:
        output.strategy = SOFTEN_MAP[output.strategy]
        output.soften_flag = True  # signals adaptation context
        return output, True

    # Even if strategy doesn't change, flag the softening for tone
    output.soften_flag = True
    return output, False


def rule_stuck_escalation(
    output: LLMReasoningOutput, state: LearnerState
) -> Tuple[LLMReasoningOutput, bool]:
    if output.classification != "STUCK":
        return output, False

    overridden = False
    if state.attempt_count >= 3:
        output.strategy = "SIMPLER_SUBPROBLEM"
        overridden = True

    if state.attempt_count >= 5:
        output.flag_for_review = True  # log for human review

    return output, overridden


def rule_challenge_gate(
    output: LLMReasoningOutput, state: LearnerState
) -> Tuple[LLMReasoningOutput, bool]:
    if output.strategy != "CHALLENGE":
        return output, False

    problem = problem_bank.get(state.current_problem_id)
    mastery = state.mastery_by_skill.get(problem.skill_code, 0.0)

    if mastery < CHALLENGE_MASTERY_THRESHOLD:
        output.strategy = "PROBE"
        return output, True

    return output, False


def rule_off_topic_redirect(
    output: LLMReasoningOutput, state: LearnerState
) -> Tuple[LLMReasoningOutput, bool]:
    if output.classification != "OFF_TOPIC":
        return output, False

    output.strategy = "REDIRECT"
    output.response = None  # response generator uses template, not LLM draft
    return output, True


def rule_correction_cycle_limit(
    output: LLMReasoningOutput, state: LearnerState
) -> Tuple[LLMReasoningOutput, bool]:
    if state.correction_cycle_count < CORRECTION_CYCLE_LIMIT:
        return output, False

    output.strategy = "SIMPLER_SUBPROBLEM"
    output.soften_flag = True
    output.flag_for_review = True
    return output, True


CONSTRAINT_PIPELINE = [
    rule_validate_output,          # Stage 1: parse guard
    rule_no_correction_on_first,   # Stage 2: pedagogical rules
    rule_no_direct_answer,
    rule_hesitation_softening,
    rule_stuck_escalation,
    rule_challenge_gate,
    rule_off_topic_redirect,
    rule_correction_cycle_limit,
]


# --- Entrypoint --------------------------------------------------------------

def enforce(
    raw_output: Optional[LLMReasoningOutput],
    state: LearnerState,
) -> OrchestratorDecision:
    output = raw_output
    overrides = []

    for rule in CONSTRAINT_PIPELINE:
        output, fired = rule(output, state)
        overrides.append(fired)

    soften = getattr(output, "soften_flag", False)
    flag_review = getattr(output, "flag_for_review", False)

    return OrchestratorDecision(
        final_strategy=output.strategy,
        policy_override=any(overrides),
        response_draft=output.response,
        adaptation_context=AdaptationContext.from_state(state, soften=soften),
        soften_flag=soften,
        flag_for_review=flag_review,
        problem_id=state.current_problem_id,
        session_id=state.session_id,
    )
