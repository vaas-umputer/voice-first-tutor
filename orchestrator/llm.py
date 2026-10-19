"""LLM reasoning call (Claude, single call per turn). See section 4 of the impl spec."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Optional, Tuple

from .models import LearnerState, LLMReasoningOutput, Problem

SYSTEM_PROMPT = """You are Priya, a warm and patient AI math tutor for Grade 8-10 students.

Teaching philosophy:
- Never give the answer directly. Always guide students to discover it themselves.
- Ask one focused question at a time. Maximum 2 sentences per response.
- Use plain language (Grade 6 reading level).
- If the student speaks in another language, respond in that language.
  Keep mathematical terms (speed, distance, formula) in English.

Response format - always return valid JSON, nothing else:
{
  "classification": "<see values below>",
  "reasoning": "<1 sentence: why you classified this way - internal only>",
  "strategy": "<see values below>",
  "response": "<your spoken response to the student>"
}

Classification values:
  CORRECT           - student's reasoning is fully correct
  PARTIALLY_CORRECT - right direction but a gap or missing step exists
  MISCONCEPTION     - student holds an identifiably wrong mental model
  STUCK             - student said "I don't know", is guessing randomly, or is silent
  CHALLENGE_READY   - student is correct AND actively seeking harder material
  OFF_TOPIC         - utterance is unrelated to the current problem

Strategy values:
  ACKNOWLEDGE       - briefly celebrate a correct answer; only use when student is clearly CORRECT or CHALLENGE_READY
  PROBE             - ask a targeted question to surface the gap
  HINT              - give a small nudge without revealing the answer
  COUNTEREXAMPLE    - offer a simpler analogous case to expose the misconception
  CORRECTION        - directly name the error (use after COUNTEREXAMPLE has failed)
  SIMPLER_SUBPROBLEM - break the problem into a smaller first step
  CHALLENGE         - introduce a harder variant
  REDIRECT          - gently bring focus back to the current problem
  NEXT_PROBLEM      - move to a new problem (only when mastery is confirmed)

Learner state field notes:
  correction_cycle_count: how many consecutive turns the learner has been corrected. If >= 3, prefer softer strategies (HINT, SIMPLER_SUBPROBLEM) over CORRECTION or PROBE.

Response constraints (enforced - do not violate):
  - response <= 40 words
  - response must end with a "?"
  - Never reveal the worked_solution, even partially
  - Never confirm a wrong answer as correct
"""

# Ollama-specific prompt — same task but with an explicit decision tree and
# few-shot examples because small local models need more scaffolding than Claude.
OLLAMA_SYSTEM_PROMPT = """You are Priya, a warm AI math tutor. Your job: read the learner's utterance and return JSON.

STEP 1 — CLASSIFY the utterance. Use EXACTLY one of these values:

  CORRECT           — learner's answer matches the worked solution (numerically or conceptually correct)
  PARTIALLY_CORRECT — learner is on the right track but incomplete or slightly off
  MISCONCEPTION     — learner states something that is factually or conceptually wrong
  STUCK             — learner says "I don't know", is silent, or gives a random guess
  CHALLENGE_READY   — learner got it right AND asks for something harder
  OFF_TOPIC         — utterance has nothing to do with math or the current problem

CLASSIFICATION DECISION TREE:
1. Does the utterance match (or closely match) the worked_solution? → CORRECT
2. Does the learner name the right method/formula but give wrong numbers or miss a step? → PARTIALLY_CORRECT
3. Does the learner state something factually wrong about math? → MISCONCEPTION
4. Does the learner say they don't know, or give a nonsense answer? → STUCK
5. Did the learner solve it AND ask for harder work? → CHALLENGE_READY
6. Is the utterance about food, weather, sports, or anything unrelated to the problem? → OFF_TOPIC

STEP 2 — PICK a strategy (EXACTLY one):
  ACKNOWLEDGE        — briefly celebrate a correct answer; only use when student is clearly CORRECT or CHALLENGE_READY
  PROBE              — ask a focused question to find the gap (used with PARTIALLY_CORRECT)
  HINT               — small nudge, don't reveal the answer (used with STUCK attempt 1-2)
  COUNTEREXAMPLE     — simpler analogous case to expose wrong thinking (used with MISCONCEPTION)
  CORRECTION         — name the error directly (used with MISCONCEPTION after COUNTEREXAMPLE failed)
  SIMPLER_SUBPROBLEM — break into a smaller step (used with STUCK attempt 3+)
  CHALLENGE          — harder variant (used with CHALLENGE_READY)
  REDIRECT           — bring focus back (used with OFF_TOPIC)
  NEXT_PROBLEM       — move on (used with CORRECT when mastery is high)

Learner state field notes:
  correction_cycle_count: how many consecutive turns the learner has been corrected. If >= 3, prefer softer strategies (HINT, SIMPLER_SUBPROBLEM) over CORRECTION or PROBE.

STEP 3 — WRITE the response:
  - Maximum 40 words
  - Must end with "?"
  - Never give the answer
  - Never say the answer is correct if it is wrong

OUTPUT FORMAT — return ONLY this JSON, nothing else:
{"classification": "...", "reasoning": "one sentence why", "strategy": "...", "response": "..."}

EXAMPLES:

# Generic examples — illustrate classification logic without referencing any specific problem.

Utterance: "The answer is [value matching the worked solution]"
{"classification": "CORRECT", "reasoning": "Learner gave the correct numeric answer matching the worked solution.", "strategy": "ACKNOWLEDGE", "response": "That's exactly right! Can you walk me through how you got there?"}

Utterance: "I think you use [correct formula or method] but I'm not sure of the final number"
{"classification": "PARTIALLY_CORRECT", "reasoning": "Learner named the right method but gave no final answer.", "strategy": "PROBE", "response": "Good thinking — you have the right approach. What answer do you get when you apply it?"}

Utterance: "I don't know"
{"classification": "STUCK", "reasoning": "Learner expressed not knowing how to proceed.", "strategy": "HINT", "response": "No problem — what information does the problem give you to start with?"}

Utterance: "I think [concept A] and [concept B] mean the same thing"
{"classification": "MISCONCEPTION", "reasoning": "Learner confused two distinct mathematical concepts.", "strategy": "COUNTEREXAMPLE", "response": "Interesting — can you think of a case where [concept A] and [concept B] would give different results?"}

# For OFF_TOPIC, leave response empty — the system fills it from a fixed template.
Utterance: "What time is it?"
{"classification": "OFF_TOPIC", "reasoning": "Utterance is unrelated to the current math problem.", "strategy": "REDIRECT", "response": ""}

Utterance: "That was easy — can you give me something harder?"
{"classification": "CHALLENGE_READY", "reasoning": "Learner solved the problem and is explicitly requesting more difficult material.", "strategy": "CHALLENGE", "response": "Love the enthusiasm — ready to tackle a trickier version of this?"}
"""

USER_TURN_TEMPLATE = """
Current problem:
  ID: {problem_id}
  Text: {problem_text}
  Worked solution (DO NOT REVEAL): {worked_solution}
  Difficulty: {difficulty}
  Concepts: {concepts}

Learner state:
  Attempt number: {attempt_count}
  Correction cycle count: {correction_cycle_count}
  Prior misconceptions this session: {misconceptions}
  Mastery on this skill: {mastery} (0.0 = unknown, 1.0 = mastered)
  Hesitation score: {hesitation_score} (0.0 = confident, 1.0 = very hesitant)

Conversation history (last 3 turns):
{history}

Current learner utterance:
  "{utterance}"

Classify and respond.
"""

# Backend selection:
#   TUTOR_LLM_BACKEND=anthropic  (default when ANTHROPIC_API_KEY is set)
#   TUTOR_LLM_BACKEND=ollama     (local Ollama; set OLLAMA_MODEL to choose model)
#   otherwise                    deterministic mock stub for testing without any key

_BACKEND = os.environ.get("TUTOR_LLM_BACKEND", "").lower()
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

_anthropic_client = None
if _BACKEND == "anthropic" or (not _BACKEND and os.environ.get("ANTHROPIC_API_KEY")):
    try:
        from anthropic import AsyncAnthropic
        _anthropic_client = AsyncAnthropic()
    except Exception:
        pass


async def reason(
    utterance: str,
    state: LearnerState,
    problem: Problem,
) -> Tuple[Optional[LLMReasoningOutput], int]:
    """
    Classify the learner utterance and pick a teaching strategy.
    Returns (output, latency_ms). Returns (None, latency_ms) on failure.

    Backends (set TUTOR_LLM_BACKEND):
      anthropic — real Claude via Anthropic API (needs ANTHROPIC_API_KEY)
      ollama    — local Ollama model (needs Ollama running; set OLLAMA_MODEL, default llama3.2)
      (unset)   — deterministic mock stub for testing without any key/server
    """
    if _anthropic_client is not None:
        return await _reason_via_anthropic(utterance, state, problem)
    if _BACKEND == "ollama":
        return await _reason_via_ollama(utterance, state, problem)
    return _reason_via_mock(utterance, state, problem)


async def _reason_via_anthropic(
    utterance: str,
    state: LearnerState,
    problem: Problem,
) -> Tuple[Optional[LLMReasoningOutput], int]:
    history_text = _format_history(state.last_3_turns)
    mastery = state.mastery_by_skill.get(problem.skill_code, 0.3)

    user_content = USER_TURN_TEMPLATE.format(
        problem_id=problem.id,
        problem_text=problem.text,
        worked_solution=problem.worked_solution,
        difficulty=problem.difficulty,
        concepts=", ".join(problem.concepts),
        attempt_count=state.attempt_count,
        correction_cycle_count=state.correction_cycle_count,
        misconceptions=("; ".join(state.misconceptions) if state.misconceptions else "none"),
        mastery=round(mastery, 2),
        hesitation_score=round(state.hesitation_score, 2),
        history=history_text,
        utterance=utterance,
    )

    t0 = time.monotonic()
    try:
        message = await _anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},  # prompt caching
                }
            ],
            messages=[{"role": "user", "content": user_content}],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        raw = message.content[0].text
        data = json.loads(raw)
        return LLMReasoningOutput(**data), latency_ms

    except Exception:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return None, latency_ms


async def _reason_via_ollama(
    utterance: str,
    state: LearnerState,
    problem: Problem,
) -> Tuple[Optional[LLMReasoningOutput], int]:
    history_text = _format_history(state.last_3_turns)
    mastery = state.mastery_by_skill.get(problem.skill_code, 0.3)

    user_content = USER_TURN_TEMPLATE.format(
        problem_id=problem.id,
        problem_text=problem.text,
        worked_solution=problem.worked_solution,
        difficulty=problem.difficulty,
        concepts=", ".join(problem.concepts),
        attempt_count=state.attempt_count,
        correction_cycle_count=state.correction_cycle_count,
        misconceptions=("; ".join(state.misconceptions) if state.misconceptions else "none"),
        mastery=round(mastery, 2),
        hesitation_score=round(state.hesitation_score, 2),
        history=history_text,
        utterance=utterance,
    )

    t0 = time.monotonic()
    try:
        import ollama as _ollama
        response = await _ollama.AsyncClient().chat(
            model=_OLLAMA_MODEL,
            format="json",
            messages=[
                {"role": "system", "content": OLLAMA_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        raw = response.message.content
        data = json.loads(raw)
        return LLMReasoningOutput(**data), latency_ms
    except Exception:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return None, latency_ms


def _format_history(turns) -> str:
    if not turns:
        return "  (no prior turns this session)"
    lines = []
    for t in turns:
        label = "Tutor" if t.role == "tutor" else "Learner"
        lines.append('  {}: "{}"'.format(label, t.text))
    return "\n".join(lines)


# --- Deterministic mock stub -------------------------------------------------
# Used only because no ANTHROPIC_API_KEY / anthropic package is available in this
# environment; keyword heuristics stand in for the real classification so the full
# pipeline (including policy overrides) can be exercised end-to-end without credentials.

_OFF_TOPIC_WORDS = ["weather", "movie", "game", "lunch", "football", "music"]
_STUCK_PHRASES = ["don't know", "dont know", "no idea", "not sure", "__silence_timeout__"]
_CHALLENGE_PHRASES = ["harder", "more difficult", "give me a challenge", "something tougher"]
_MISCONCEPTION_PHRASES = ["speed is just how far", "distance is the same as speed", "time doesn't matter"]

_NUMBER_RE = re.compile(r"-?\d+(\.\d+)?")


def _reason_via_mock(
    utterance: str,
    state: LearnerState,
    problem: Problem,
) -> Tuple[Optional[LLMReasoningOutput], int]:
    t0 = time.monotonic()
    text = utterance.lower()

    if any(w in text for w in _OFF_TOPIC_WORDS):
        output = LLMReasoningOutput(
            classification="OFF_TOPIC",
            strategy="REDIRECT",
            reasoning="mock_stub: utterance mentions an unrelated topic",
            response="Let's get back to the problem — what do you think the next step is?",
        )
    elif any(p in text for p in _CHALLENGE_PHRASES):
        output = LLMReasoningOutput(
            classification="CHALLENGE_READY",
            strategy="CHALLENGE",
            reasoning="mock_stub: learner explicitly asked for harder material",
            response="Ready for something tougher — want to try a two-part speed problem?",
        )
    elif any(p in text for p in _STUCK_PHRASES):
        output = LLMReasoningOutput(
            classification="STUCK",
            strategy="HINT",
            reasoning="mock_stub: learner expressed not knowing how to proceed",
            response="No worries — what two numbers from the problem do you think you'd combine?",
        )
    elif any(p in text for p in _MISCONCEPTION_PHRASES):
        output = LLMReasoningOutput(
            classification="MISCONCEPTION",
            strategy="COUNTEREXAMPLE",
            reasoning="mock_stub: utterance matches a known wrong mental model",
            response="If you walked 10 km in 1 hour versus 10 km in 2 hours, would your speed be the same?",
        )
    elif "divide" in text or "divided" in text or "/" in text:
        # Plausible correct method mentioned, but no final numeric answer given yet.
        output = LLMReasoningOutput(
            classification="PARTIALLY_CORRECT",
            strategy="PROBE",
            reasoning="mock_stub: learner named the right operation but gave no final answer",
            response="Good start — dividing distance by time. What number do you get when you do that?",
        )
    elif _NUMBER_RE.search(text):
        output = LLMReasoningOutput(
            classification="CORRECT",
            strategy="ACKNOWLEDGE",
            reasoning="mock_stub: learner supplied a numeric answer",
            response="Nice work — that's the right speed! Ready to try the next problem?",
        )
    else:
        output = LLMReasoningOutput(
            classification="STUCK",
            strategy="HINT",
            reasoning="mock_stub: utterance did not match any known pattern",
            response="Let's take it step by step — what information does the problem give you?",
        )

    latency_ms = int((time.monotonic() - t0) * 1000)
    return output, latency_ms
