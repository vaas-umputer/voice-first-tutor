"""Tests for llm.py — LLM reasoning module.

Covers:
  - Mock stub (no backend set): reason() returns a valid LLMReasoningOutput
  - Ollama backend failure: reason() returns (None, latency_ms), not an exception
  - Mock stub heuristics: STUCK, PARTIALLY_CORRECT, OFF_TOPIC, CORRECT classifications
"""

from __future__ import annotations

import asyncio
import sys
import unittest.mock as mock

import pytest

from orchestrator.models import LearnerState, LLMReasoningOutput, Problem
from orchestrator.llm import _reason_via_mock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(**overrides) -> LearnerState:
    defaults = dict(
        session_id="sess_test",
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


def make_problem(**overrides) -> Problem:
    defaults = dict(
        id="prob_001",
        text="A train travels 60 km in 2 hours. What is its speed?",
        skill_code="math.ratio.speed_distance_time",
        difficulty="easy",
        worked_solution="speed = distance / time = 60 / 2 = 30 km/h",
        concepts=["division", "ratio", "units"],
    )
    defaults.update(overrides)
    return Problem(**defaults)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 1. Mock stub (no backend) — reason() returns valid LLMReasoningOutput
# ---------------------------------------------------------------------------

def test_mock_stub_returns_valid_output(monkeypatch):
    """With TUTOR_LLM_BACKEND unset and no ANTHROPIC_API_KEY, reason() uses the
    mock stub and returns a valid (LLMReasoningOutput, latency_ms) tuple."""
    monkeypatch.delenv("TUTOR_LLM_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Re-import llm so module-level _BACKEND / _anthropic_client reflect env changes.
    import importlib
    import orchestrator.llm as llm_mod
    importlib.reload(llm_mod)

    state = make_state()
    problem = make_problem()

    output, latency_ms = run(llm_mod.reason("I don't know", state, problem))

    assert output is not None
    assert isinstance(output, LLMReasoningOutput)
    assert output.classification in {
        "CORRECT", "PARTIALLY_CORRECT", "MISCONCEPTION",
        "STUCK", "CHALLENGE_READY", "OFF_TOPIC",
    }
    assert isinstance(latency_ms, int)


def test_unknown_backend_uses_mock(monkeypatch):
    """An unrecognised backend string (not anthropic/ollama) still reaches the
    mock stub rather than raising."""
    monkeypatch.setenv("TUTOR_LLM_BACKEND", "nonexistent_backend")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import importlib
    import orchestrator.llm as llm_mod
    importlib.reload(llm_mod)

    state = make_state()
    problem = make_problem()
    output, latency_ms = run(llm_mod.reason("42", state, problem))

    assert output is not None
    assert isinstance(output, LLMReasoningOutput)


# ---------------------------------------------------------------------------
# 2. Ollama backend failure — reason() returns (None, latency_ms)
# ---------------------------------------------------------------------------

def test_ollama_failure_returns_none_not_exception(monkeypatch):
    """When TUTOR_LLM_BACKEND=ollama but the Ollama server raises, _reason_via_ollama
    must return (None, latency_ms) — no exception propagated to the caller."""
    monkeypatch.setenv("TUTOR_LLM_BACKEND", "ollama")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import importlib
    import orchestrator.llm as llm_mod
    importlib.reload(llm_mod)

    # Patch the ollama package at the sys.modules level so that the
    # `import ollama as _ollama` inside _reason_via_ollama gets our mock.
    async def _bad_chat(*args, **kwargs):
        raise RuntimeError("connection refused")

    bad_client = mock.MagicMock()
    bad_client.chat = _bad_chat
    mock_ollama = mock.MagicMock()
    mock_ollama.AsyncClient.return_value = bad_client
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama)

    state = make_state()
    problem = make_problem()

    # _reason_via_ollama's internal try/except should absorb the error.
    output, latency_ms = run(llm_mod._reason_via_ollama("hello", state, problem))

    assert output is None
    assert isinstance(latency_ms, int)


# ---------------------------------------------------------------------------
# 3. Mock stub heuristics — test _reason_via_mock directly (synchronous)
# ---------------------------------------------------------------------------

def test_mock_stub_stuck_on_dont_know():
    state = make_state()
    problem = make_problem()
    output, latency = _reason_via_mock("I don't know", state, problem)
    assert output.classification == "STUCK"
    assert isinstance(latency, int)


def test_mock_stub_partially_correct_on_divide():
    state = make_state()
    problem = make_problem()
    output, latency = _reason_via_mock("I think I need to divide the numbers", state, problem)
    assert output.classification == "PARTIALLY_CORRECT"


def test_mock_stub_off_topic_on_weather():
    state = make_state()
    problem = make_problem()
    output, latency = _reason_via_mock("What is the weather today?", state, problem)
    assert output.classification == "OFF_TOPIC"
    assert output.strategy == "REDIRECT"


def test_mock_stub_correct_on_numeric_answer():
    state = make_state()
    problem = make_problem()
    output, latency = _reason_via_mock("The speed is 30", state, problem)
    assert output.classification == "CORRECT"
    assert output.strategy == "ACKNOWLEDGE"


def test_mock_stub_stuck_on_unrecognised_utterance():
    """An utterance that matches no keyword pattern defaults to STUCK."""
    state = make_state()
    problem = make_problem()
    output, latency = _reason_via_mock("hmm", state, problem)
    assert output.classification == "STUCK"


def test_mock_stub_challenge_ready():
    state = make_state()
    problem = make_problem()
    output, latency = _reason_via_mock("Can you give me a challenge?", state, problem)
    assert output.classification == "CHALLENGE_READY"
    assert output.strategy == "CHALLENGE"


def test_mock_stub_misconception():
    state = make_state()
    problem = make_problem()
    output, latency = _reason_via_mock("speed is just how far you go", state, problem)
    assert output.classification == "MISCONCEPTION"
    assert output.strategy == "COUNTEREXAMPLE"


def test_mock_stub_latency_is_non_negative():
    state = make_state()
    problem = make_problem()
    _, latency = _reason_via_mock("some utterance", state, problem)
    assert latency >= 0


def test_mock_stub_response_ends_with_question_mark():
    """The mock stub's response field should always end with '?'."""
    utterances = [
        "I don't know",
        "divide",
        "weather",
        "30",
        "hmm",
        "harder",
        "speed is just how far",
    ]
    state = make_state()
    problem = make_problem()
    for utt in utterances:
        output, _ = _reason_via_mock(utt, state, problem)
        assert output.response.endswith("?"), (
            f"response for '{utt}' does not end with '?': {output.response!r}"
        )
