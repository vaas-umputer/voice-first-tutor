"""Tests for response.py — response generation module.

All tests run against the fallback path (no ANTHROPIC_API_KEY in env).
"""

from __future__ import annotations

import asyncio
import os
import pytest

from orchestrator import response
from orchestrator.models import AdaptationContext, OrchestratorDecision, Problem
from orchestrator.response import (
    REDIRECT_TEMPLATE,
    STRATEGY_GUIDANCE,
    _build_user_prompt,
    _shorten_problem_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(**overrides) -> AdaptationContext:
    defaults = dict(language="en", pace="normal", style="concise", soften=False)
    defaults.update(overrides)
    return AdaptationContext(**defaults)


def make_decision(**overrides) -> OrchestratorDecision:
    defaults = dict(
        final_strategy="HINT",
        policy_override=False,
        response_draft="Can you think about what happens when x=0?",
        adaptation_context=make_ctx(),
        soften_flag=False,
        flag_for_review=False,
        problem_id="prob_001",
        session_id="sess_1",
    )
    defaults.update(overrides)
    return OrchestratorDecision(**defaults)


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
    """Run a coroutine synchronously for testing."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 1. Fallback with draft present
# ---------------------------------------------------------------------------

def test_fallback_returns_draft_when_present(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    draft = "Can you think about what happens when x=0?"
    decision = make_decision(response_draft=draft)
    problem = make_problem()

    text, latency = run(response.generate(decision, problem))

    assert text == draft
    assert latency == 0


# ---------------------------------------------------------------------------
# 2. Fallback with no draft (OFF_TOPIC / REDIRECT case)
# ---------------------------------------------------------------------------

def test_fallback_no_draft_uses_redirect_template(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    decision = make_decision(
        final_strategy="REDIRECT",
        response_draft=None,
    )
    problem = make_problem(text="A train travels 60 km in 2 hours. What is its speed?")

    text, latency = run(response.generate(decision, problem))

    # Should contain the REDIRECT_TEMPLATE scaffolding text
    assert "stay focused" in text
    # Should mention a shortened version of the problem
    assert "train" in text or "a train" in text
    assert latency == 0


# ---------------------------------------------------------------------------
# 3. _shorten_problem_text
# ---------------------------------------------------------------------------

def test_shorten_short_text_unchanged():
    short = "What is 2+2?"
    result = _shorten_problem_text(short)
    # Trailing punctuation stripped, lowercased
    assert result == "what is 2+2"


def test_shorten_long_text_truncated_at_word_boundary():
    # Build a text definitely longer than 60 chars
    long_text = "A train leaves station X and travels to station Y at a constant speed of 60 km per hour."
    result = _shorten_problem_text(long_text)
    assert result.endswith("...")
    assert len(result) <= 60 + len("...")
    # Must not cut in the middle of a word (no partial word before "...")
    without_ellipsis = result[:-3]
    assert not without_ellipsis.endswith(" ")


def test_shorten_exactly_60_chars_not_truncated():
    text = "a" * 60  # exactly 60 chars, no trailing punctuation
    result = _shorten_problem_text(text)
    assert not result.endswith("...")
    assert result == text.lower()


# ---------------------------------------------------------------------------
# 4. _build_user_prompt includes strategy, language, soften, problem text
# ---------------------------------------------------------------------------

def test_build_user_prompt_contains_strategy():
    decision = make_decision(final_strategy="PROBE")
    problem = make_problem()
    prompt = _build_user_prompt(decision, problem)
    assert "STRATEGY: PROBE" in prompt


def test_build_user_prompt_contains_language():
    decision = make_decision(adaptation_context=make_ctx(language="en"))
    problem = make_problem()
    prompt = _build_user_prompt(decision, problem)
    assert "LANGUAGE: English" in prompt


def test_build_user_prompt_contains_soften_flag():
    decision = make_decision(adaptation_context=make_ctx(soften=True))
    problem = make_problem()
    prompt = _build_user_prompt(decision, problem)
    assert "SOFTEN: true" in prompt


def test_build_user_prompt_contains_problem_text():
    problem = make_problem(text="What is 5 * 6?")
    decision = make_decision()
    prompt = _build_user_prompt(decision, problem)
    assert "What is 5 * 6?" in prompt


# ---------------------------------------------------------------------------
# 5. _build_user_prompt includes draft when response_draft is set
# ---------------------------------------------------------------------------

def test_build_user_prompt_includes_draft():
    draft = "Try thinking about the formula for speed."
    decision = make_decision(response_draft=draft)
    problem = make_problem()
    prompt = _build_user_prompt(decision, problem)
    assert draft in prompt
    assert "SUGGESTED DRAFT" in prompt


# ---------------------------------------------------------------------------
# 6. _build_user_prompt omits draft section when response_draft is None
# ---------------------------------------------------------------------------

def test_build_user_prompt_omits_draft_when_none():
    decision = make_decision(response_draft=None)
    problem = make_problem()
    prompt = _build_user_prompt(decision, problem)
    assert "SUGGESTED DRAFT" not in prompt


# ---------------------------------------------------------------------------
# 7. Language mapping
# ---------------------------------------------------------------------------

def test_language_english_maps_to_full_name():
    decision = make_decision(adaptation_context=make_ctx(language="en"))
    prompt = _build_user_prompt(decision, make_problem())
    assert "LANGUAGE: English" in prompt


def test_language_hindi_maps_to_full_name():
    decision = make_decision(adaptation_context=make_ctx(language="hi"))
    prompt = _build_user_prompt(decision, make_problem())
    assert "LANGUAGE: Hindi" in prompt


def test_language_tamil_maps_to_full_name():
    decision = make_decision(adaptation_context=make_ctx(language="ta"))
    prompt = _build_user_prompt(decision, make_problem())
    assert "LANGUAGE: Tamil" in prompt


# ---------------------------------------------------------------------------
# 8. Soften flag in prompt
# ---------------------------------------------------------------------------

def test_soften_true_produces_true_in_prompt():
    decision = make_decision(adaptation_context=make_ctx(soften=True))
    prompt = _build_user_prompt(decision, make_problem())
    assert "SOFTEN: true" in prompt


def test_soften_false_produces_false_in_prompt():
    decision = make_decision(adaptation_context=make_ctx(soften=False))
    prompt = _build_user_prompt(decision, make_problem())
    assert "SOFTEN: false" in prompt


# ---------------------------------------------------------------------------
# 9. All 9 strategies have entries in STRATEGY_GUIDANCE
# ---------------------------------------------------------------------------

ALL_STRATEGIES = [
    "ACKNOWLEDGE",
    "PROBE",
    "HINT",
    "COUNTEREXAMPLE",
    "CORRECTION",
    "SIMPLER_SUBPROBLEM",
    "CHALLENGE",
    "REDIRECT",
    "NEXT_PROBLEM",
]


@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_strategy_guidance_has_entry(strategy):
    assert strategy in STRATEGY_GUIDANCE, f"STRATEGY_GUIDANCE missing key: {strategy}"
    assert STRATEGY_GUIDANCE[strategy], f"STRATEGY_GUIDANCE entry for {strategy} is empty"


# ---------------------------------------------------------------------------
# 10. Ollama backend — falls back to draft when Ollama call raises
# ---------------------------------------------------------------------------

def _make_bad_ollama_module():
    """Return a mock ollama module whose AsyncClient().chat always raises."""
    import unittest.mock as mock

    async def _bad_chat(*args, **kwargs):
        raise ConnectionError("Ollama not reachable")

    mock_client = mock.MagicMock()
    mock_client.chat = _bad_chat
    mock_ollama = mock.MagicMock()
    mock_ollama.AsyncClient.return_value = mock_client
    return mock_ollama


def test_ollama_failure_falls_back_to_draft(monkeypatch):
    """When TUTOR_LLM_BACKEND=ollama and the underlying Ollama chat call raises,
    generate() should return the response_draft (fallback path), not propagate."""
    monkeypatch.setenv("TUTOR_LLM_BACKEND", "ollama")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "ollama", _make_bad_ollama_module())

    draft = "What does dividing distance by time give you?"
    decision = make_decision(response_draft=draft)
    problem = make_problem()

    text, latency = run(response.generate(decision, problem))

    assert text == draft
    assert latency == 0


def test_ollama_failure_no_draft_uses_redirect(monkeypatch):
    """When Ollama fails and there is no draft, generate() uses the REDIRECT template."""
    monkeypatch.setenv("TUTOR_LLM_BACKEND", "ollama")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "ollama", _make_bad_ollama_module())

    decision = make_decision(final_strategy="REDIRECT", response_draft=None)
    problem = make_problem(text="A train travels 60 km in 2 hours. What is its speed?")

    text, latency = run(response.generate(decision, problem))

    assert "stay focused" in text
    assert latency == 0


def test_ollama_generate_via_ollama_returns_none_on_exception(monkeypatch):
    """_generate_via_ollama returns (None, latency_ms) when ollama raises, not an exception."""
    monkeypatch.setenv("TUTOR_LLM_BACKEND", "ollama")
    monkeypatch.setitem(__import__("sys").modules, "ollama", _make_bad_ollama_module())

    decision = make_decision()
    problem = make_problem()

    text, latency = run(response._generate_via_ollama(decision, problem))

    assert text is None
    assert isinstance(latency, int)


# ---------------------------------------------------------------------------
# 11. Anthropic backend — falls back to draft when Claude call raises
# ---------------------------------------------------------------------------

def test_anthropic_failure_falls_back_to_draft(monkeypatch):
    """When TUTOR_LLM_BACKEND=anthropic and the Claude call raises, generate()
    should fall back to the response_draft, not propagate the exception."""
    monkeypatch.setenv("TUTOR_LLM_BACKEND", "anthropic")
    # Provide a fake key so the anthropic branch is entered.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")

    draft = "Think about the formula: speed = distance / time."
    decision = make_decision(response_draft=draft)
    problem = make_problem()

    # Patch _generate_via_claude to simulate an API failure returning (None, ms).
    async def _failing_claude(dec, prob):
        return None, 50

    monkeypatch.setattr(response, "_generate_via_claude", _failing_claude)

    text, latency = run(response.generate(decision, problem))

    assert text == draft
    assert latency == 0


def test_anthropic_generate_via_claude_returns_none_on_exception(monkeypatch):
    """_generate_via_claude returns (None, latency_ms) when the API raises."""
    monkeypatch.setenv("TUTOR_LLM_BACKEND", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")

    decision = make_decision()
    problem = make_problem()

    import unittest.mock as mock

    # Mock the AsyncAnthropic client so messages.create raises.
    async def _bad_create(*args, **kwargs):
        raise RuntimeError("simulated API error")

    mock_messages = mock.MagicMock()
    mock_messages.create = _bad_create
    mock_client_instance = mock.MagicMock()
    mock_client_instance.messages = mock_messages
    mock_anthropic_cls = mock.MagicMock(return_value=mock_client_instance)
    mock_anthropic_module = mock.MagicMock()
    mock_anthropic_module.AsyncAnthropic = mock_anthropic_cls

    monkeypatch.setitem(__import__("sys").modules, "anthropic", mock_anthropic_module)

    text, latency = run(response._generate_via_claude(decision, problem))

    assert text is None
    assert isinstance(latency, int)
