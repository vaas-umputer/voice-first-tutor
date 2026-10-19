"""
Response generation module.

Two-call architecture:
  llm.py    → "what should I do?" (classifies utterance, picks strategy)
  response.py → "how should I say it?" (generates the final spoken words)

When ANTHROPIC_API_KEY is set, this makes a second Claude call per turn that
takes the strategy + adaptation context (language, pace, soften, style) and
generates a properly toned, language-aware spoken response.

When no API key is present, falls back to returning the response_draft from
llm.py as-is (or the REDIRECT_TEMPLATE for OFF_TOPIC with no draft).
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional, Tuple

from .models import AdaptationContext, OrchestratorDecision, Problem

REDIRECT_TEMPLATE = (
    "Let's stay focused on our problem for now — "
    "we were working on {problem_short}. Where were we?"
)

_PROBLEM_SHORT_MAX_CHARS = 60

RESPONSE_SYSTEM_PROMPT = """\
You are Priya, a warm and patient AI math tutor for Grade 8–10 students.
Your job right now is NOT to reason about the learner's answer — that has already been done.
Your job is to deliver one spoken response to the learner, following the exact strategy given to you.

Rules you must never break:
- Never give the answer directly, even partially.
- Never confirm a wrong answer as correct.
- Respond in the learner's language (see LANGUAGE below). Keep mathematical terms in English.
- Maximum 2 sentences. Maximum 40 words. Must end with a "?".
- If soften=true, open with a brief empathy phrase (e.g. "I can see you're thinking hard about this —").
- If style=detailed, give a bit more scaffolding in your response. If style=concise, keep it tight.
- If pace=slow, use simpler shorter sentences.
- If pace=fast, be concise and skip the scaffolding preamble.

Return ONLY the spoken response text — no JSON, no labels, no explanation.
"""

STRATEGY_GUIDANCE = {
    "ACKNOWLEDGE":        "Briefly celebrate what the learner got right, then move forward.",
    "PROBE":              "Ask one targeted question to surface the gap in understanding.",
    "HINT":               "Give a small nudge toward the right approach without revealing the answer.",
    "COUNTEREXAMPLE":     "Offer a simpler analogous case to expose the misconception.",
    "CORRECTION":         "Directly but kindly name the error. Do not give the answer.",
    "SIMPLER_SUBPROBLEM": "Break the problem into a smaller, easier first step and ask about that.",
    "CHALLENGE":          "Introduce a harder variant or extension of the problem.",
    "REDIRECT":           "Gently bring the learner's focus back to the current problem.",
    "NEXT_PROBLEM":       "Acknowledge mastery and signal you are moving to the next problem.",
}

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
}


def _shorten_problem_text(text: str) -> str:
    if len(text) <= _PROBLEM_SHORT_MAX_CHARS:
        return text.rstrip(".?!").lower()
    return text[:_PROBLEM_SHORT_MAX_CHARS].rsplit(" ", 1)[0].rstrip(".?!").lower() + "..."


def _build_user_prompt(
    decision: OrchestratorDecision,
    problem: Problem,
) -> str:
    ctx = decision.adaptation_context
    lang_name = LANGUAGE_NAMES.get(ctx.language, ctx.language)
    guidance = STRATEGY_GUIDANCE.get(decision.final_strategy, "Guide the learner.")

    lines = [
        f"STRATEGY: {decision.final_strategy}",
        f"STRATEGY GUIDANCE: {guidance}",
        f"LANGUAGE: {lang_name}",
        f"PACE: {ctx.pace}",
        f"STYLE: {ctx.style}",
        f"SOFTEN: {'true' if ctx.soften else 'false'}",
        "",
        f"CURRENT PROBLEM: {problem.text}",
        f"PROBLEM CONCEPTS: {', '.join(problem.concepts)}",
    ]

    if decision.response_draft:
        lines += [
            "",
            f"SUGGESTED DRAFT (you may rewrite for tone/language, but keep the same intent):",
            f"  \"{decision.response_draft}\"",
        ]

    return "\n".join(lines)


async def generate(decision: OrchestratorDecision, problem: Problem) -> Tuple[str, int]:
    """
    Generate the final spoken response text.

    Returns (response_text, latency_ms).

    Backends (set TUTOR_LLM_BACKEND):
      anthropic — real Claude (needs ANTHROPIC_API_KEY)
      ollama    — local Ollama model (needs Ollama running; set OLLAMA_MODEL)
      (unset)   — fallback: return the draft from llm.py as-is
    """
    backend = os.environ.get("TUTOR_LLM_BACKEND", "").lower()

    if backend == "anthropic" or (not backend and os.environ.get("ANTHROPIC_API_KEY")):
        text, latency = await _generate_via_claude(decision, problem)
        if text:
            return text, latency

    if backend == "ollama":
        text, latency = await _generate_via_ollama(decision, problem)
        if text:
            return text, latency

    return _fallback_response(decision, problem), 0


async def _generate_via_claude(
    decision: OrchestratorDecision,
    problem: Problem,
) -> Tuple[Optional[str], int]:
    t0 = time.monotonic()
    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic()
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=120,
            system=[
                {
                    "type": "text",
                    "text": RESPONSE_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": _build_user_prompt(decision, problem),
                }
            ],
        )
        latency = int((time.monotonic() - t0) * 1000)
        text = message.content[0].text.strip()
        return text, latency
    except Exception:
        latency = int((time.monotonic() - t0) * 1000)
        return None, latency


async def _generate_via_ollama(
    decision: OrchestratorDecision,
    problem: Problem,
) -> Tuple[Optional[str], int]:
    t0 = time.monotonic()
    try:
        import ollama as _ollama
        model = os.environ.get("OLLAMA_MODEL", "llama3.2")
        response = await _ollama.AsyncClient().chat(
            model=model,
            messages=[
                {"role": "system", "content": RESPONSE_SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(decision, problem)},
            ],
        )
        latency = int((time.monotonic() - t0) * 1000)
        text = response.message.content.strip()
        return text, latency
    except Exception:
        latency = int((time.monotonic() - t0) * 1000)
        return None, latency


def _fallback_response(decision: OrchestratorDecision, problem: Problem) -> str:
    if decision.response_draft is not None:
        return decision.response_draft
    problem_short = _shorten_problem_text(problem.text)
    return REDIRECT_TEMPLATE.format(problem_short=problem_short)
