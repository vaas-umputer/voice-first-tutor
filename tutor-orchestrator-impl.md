# Tutor Orchestrator — Implementation Reference

**Version:** 2.0  
**Status:** Implementation-Ready  
**Scope:** `orchestrator/` package only — everything Vaasini owns (VT-05 through VT-08)  
**Boundary:** Orchestrator receives a `validated_utterance: str` from the Turn Manager and returns a `TutorResponse` to the Response Generator. It does not own audio, WebSocket, STT, or TTS.

---

## Table of Contents

1. [Package Structure](#1-package-structure)
2. [Data Contracts](#2-data-contracts)
3. [Module: Problem Bank (VT-05)](#3-module-problem-bank-vt-05)
4. [Module: LLM Reasoning (VT-06)](#4-module-llm-reasoning-vt-06)
5. [Module: Policy Engine (VT-07)](#5-module-policy-engine-vt-07)
6. [Module: Learner State and BKT (VT-08)](#6-module-learner-state-and-bkt-vt-08)
7. [Module: Trace Logger](#7-module-trace-logger)
8. [Public Entry Point](#8-public-entry-point)
9. [Exception Paths](#9-exception-paths)
10. [Unit Test Checklist](#10-unit-test-checklist)
11. [Integration Contract with Varshini's Pipeline](#11-integration-contract-with-varshinis-pipeline)

---

## 1. Package Structure

```
orchestrator/
├── __init__.py          ← exposes process_turn() — the only public function
├── models.py            ← all dataclasses / TypedDicts; no logic
├── problems.json        ← static problem bank (authored, not generated)
├── problem_bank.py      ← loads and queries problems.json
├── llm.py               ← LLM reasoning call (Claude, single call per turn)
├── policy.py            ← constraint pipeline (pure Python, no I/O)
├── state.py             ← LearnerState struct + BKT update + difficulty selection
├── response.py          ← assembles final prompt from decision + adaptation context
└── trace.py             ← writes OrchestratorTrace to SQLite per turn
```

Nothing outside this package reads `llm.py`, `policy.py`, `state.py`, `response.py`, or `trace.py` directly.  
The only public surface is `process_turn()` in `__init__.py`.

---

## 2. Data Contracts

All structs live in `models.py`. Import from there everywhere — never redefine inline.

### 2.1 LearnerState

The full state of one learner in one session. Owned by `state.py`. Written to SQLite on session end.

```python
@dataclass
class LearnerState:
    session_id: str
    topic: str                          # e.g. "math.ratio.speed_distance_time"
    language: str                       # BCP-47: "en", "hi", "ta"
    level: Literal["easy", "medium", "hard"]
    current_problem_id: str
    attempt_count: int                  # resets on new problem
    correction_cycle_count: int         # resets on CORRECT / CHALLENGE_READY
    mastery_by_skill: dict[str, float]  # skill_code → p_know (0.0–1.0)
    misconceptions: list[str]           # accumulated this session
    hesitation_score: float             # 0.0–1.0; set by Turn Manager before handoff
    last_3_turns: list[Turn]            # rolling window; updated after each turn

@dataclass
class Turn:
    role: Literal["tutor", "learner"]
    text: str
    timestamp: datetime
```

### 2.2 Problem

One entry from `problems.json`. Loaded by `problem_bank.py` at startup — never re-read from disk at runtime.

```python
@dataclass
class Problem:
    id: str                   # e.g. "prob_007"
    text: str                 # the question shown/spoken to the learner
    skill_code: str           # e.g. "math.ratio.speed_distance_time"
    difficulty: Literal["easy", "medium", "hard"]
    worked_solution: str      # NEVER sent to learner; injected into LLM prompt only
    concepts: list[str]       # e.g. ["division", "ratio", "units"]
```

### 2.3 LLMReasoningOutput

What the LLM call returns after JSON parsing. If parsing fails, `policy.py` never sees this — a fallback is synthesised directly.

```python
@dataclass
class LLMReasoningOutput:
    classification: Literal[
        "CORRECT",
        "PARTIALLY_CORRECT",
        "MISCONCEPTION",
        "STUCK",
        "CHALLENGE_READY",
        "OFF_TOPIC",
    ]
    strategy: Literal[
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
    reasoning: str       # 1 sentence, internal only — never reaches learner
    response: str | None # raw draft ≤ 40 words, ends with "?"; None on some overrides
```

### 2.4 AdaptationContext

Assembled deterministically from `LearnerState` by `AdaptationContext.from_state()`. Travels alongside `final_strategy` into the response generator. Never modified by the policy engine — the policy engine sets flags that `AdaptationContext` reads.

```python
@dataclass
class AdaptationContext:
    language: str                           # BCP-47 — drives language directive
    pace: Literal["slow", "normal", "fast"] # derived from hesitation_score
    style: Literal["concise", "detailed"]   # derived from attempt_count
    soften: bool                            # set True by Rule 3 (hesitation)

    @classmethod
    def from_state(cls, state: LearnerState, soften: bool = False) -> "AdaptationContext":
        pace = "slow" if state.hesitation_score > 0.6 else "normal"
        style = "detailed" if state.attempt_count >= 3 else "concise"
        return cls(
            language=state.language,
            pace=pace,
            style=style,
            soften=soften,
        )
```

### 2.5 OrchestratorDecision

The policy engine's output. Contains everything the response generator needs. Written to the trace log immediately.

```python
@dataclass
class OrchestratorDecision:
    final_strategy: str          # one of the strategy enum values
    policy_override: bool        # True if any constraint rule fired
    response_draft: str | None   # None → response generator builds from strategy template
    adaptation_context: AdaptationContext
    soften_flag: bool            # True → prepend effort acknowledgment
    flag_for_review: bool        # True → log for human review (correction_cycle >= 5)
    problem_id: str
    session_id: str
```

### 2.6 OrchestratorTrace

Written to SQLite every turn via `trace.py`. Primary debugging artifact — not a side-effect log.

```python
@dataclass
class OrchestratorTrace:
    session_id: str
    turn_index: int
    utterance: str               # "__silence_timeout__" on timeout path
    stt_confidence: float
    hesitation_score: float
    llm_classification: str
    llm_strategy: str
    policy_override: bool
    final_strategy: str
    response: str
    adaptation_applied: dict     # serialised AdaptationContext
    latency_llm_ms: int
    latency_tts_ms: int          # filled by response.py after TTS call
    latency_e2e_ms: int          # filled by __init__.py at turn end
    timestamp: datetime
```

---

## 3. Module: Problem Bank (VT-05)

**File:** `problem_bank.py`  
**Acceptance:** ≥ 10 problems authored, 3 difficulty levels, one skill cluster for MVP demo.

### 3.1 JSON Schema

Each entry in `problems.json`:

```json
{
  "id": "prob_007",
  "text": "A train travels 240 km in 3 hours. What is its average speed?",
  "skill_code": "math.ratio.speed_distance_time",
  "difficulty": "medium",
  "worked_solution": "speed = distance / time = 240 / 3 = 80 km/h",
  "concepts": ["division", "ratio", "units", "speed-distance-time"]
}
```

**`worked_solution` rules:**
- Written as step-by-step working, not just the final answer.
- Injected into the LLM system prompt. Never appears in any field the learner sees or hears.
- Must be mathematically verified before committing to the file.

### 3.2 problem_bank.py

```python
import json
from pathlib import Path
from models import Problem

_BANK: dict[str, Problem] = {}

def load() -> None:
    """Call once at application startup."""
    path = Path(__file__).parent / "problems.json"
    data = json.loads(path.read_text())
    for entry in data:
        p = Problem(**entry)
        _BANK[p.id] = p

def get(problem_id: str) -> Problem:
    return _BANK[problem_id]

def select_for_level(level: str, exclude_ids: list[str] = []) -> Problem:
    """Return a random problem at the given difficulty, excluding already-seen ones."""
    import random
    candidates = [
        p for p in _BANK.values()
        if p.difficulty == level and p.id not in exclude_ids
    ]
    if not candidates:
        # All problems at this level exhausted — wrap around
        candidates = [p for p in _BANK.values() if p.difficulty == level]
    return random.choice(candidates)
```

---

## 4. Module: LLM Reasoning (VT-06)

**File:** `llm.py`  
**Acceptance:** ≥ 85% correct classification on scripted utterances before wiring to policy.

### 4.1 System Prompt (cached)

Sent once per session. Mark as `cache_control: ephemeral` in the Anthropic API call to get prompt caching benefits (~90% cache hit after the first turn).

```
You are Priya, a warm and patient AI math tutor for Grade 8–10 students.

Teaching philosophy:
- Never give the answer directly. Always guide students to discover it themselves.
- Ask one focused question at a time. Maximum 2 sentences per response.
- Use plain language (Grade 6 reading level).
- If the student speaks in another language, respond in that language.
  Keep mathematical terms (speed, distance, formula) in English.

Response format — always return valid JSON, nothing else:
{
  "classification": "<see values below>",
  "reasoning": "<1 sentence: why you classified this way — internal only>",
  "strategy": "<see values below>",
  "response": "<your spoken response to the student>"
}

Classification values:
  CORRECT           — student's reasoning is fully correct
  PARTIALLY_CORRECT — right direction but a gap or missing step exists
  MISCONCEPTION     — student holds an identifiably wrong mental model
  STUCK             — student said "I don't know", is guessing randomly, or is silent
  CHALLENGE_READY   — student is correct AND actively seeking harder material
  OFF_TOPIC         — utterance is unrelated to the current problem

Strategy values:
  ACKNOWLEDGE       — briefly celebrate; pair with PROBE or NEXT_PROBLEM
  PROBE             — ask a targeted question to surface the gap
  HINT              — give a small nudge without revealing the answer
  COUNTEREXAMPLE    — offer a simpler analogous case to expose the misconception
  CORRECTION        — directly name the error (use after COUNTEREXAMPLE has failed)
  SIMPLER_SUBPROBLEM — break the problem into a smaller first step
  CHALLENGE         — introduce a harder variant
  REDIRECT          — gently bring focus back to the current problem
  NEXT_PROBLEM      — move to a new problem (only when mastery is confirmed)

Response constraints (enforced — do not violate):
  - response ≤ 40 words
  - response must end with a "?"
  - Never reveal the worked_solution, even partially
  - Never confirm a wrong answer as correct
```

### 4.2 User Turn Template

Assembled fresh every turn. `last_3_turns` is the only history passed — do not pass full session history.

```python
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
```

### 4.3 llm.py

```python
import json
import time
from anthropic import AsyncAnthropic
from models import LearnerState, LLMReasoningOutput, Problem

client = AsyncAnthropic()
SYSTEM_PROMPT = "..."  # the full system prompt above

async def reason(
    utterance: str,
    state: LearnerState,
    problem: Problem,
) -> tuple[LLMReasoningOutput | None, int]:
    """
    Call Claude once. Returns (output, latency_ms).
    Returns (None, latency_ms) on any failure — caller synthesises fallback.
    """
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
        misconceptions=state.misconceptions or "none",
        mastery=round(mastery, 2),
        hesitation_score=round(state.hesitation_score, 2),
        history=history_text,
        utterance=utterance,
    )

    t0 = time.monotonic()
    try:
        message = await client.messages.create(
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


def _format_history(turns) -> str:
    if not turns:
        return "  (no prior turns this session)"
    lines = []
    for t in turns:
        label = "Tutor" if t.role == "tutor" else "Learner"
        lines.append(f"  {label}: \"{t.text}\"")
    return "\n".join(lines)
```

**Testing `llm.py` before wiring policy:**  
Run it against these scripted utterances and verify classifications manually:

| Utterance | Expected classification | Expected strategy |
|---|---|---|
| `"I think you divide distance by time?"` | PARTIALLY_CORRECT | PROBE |
| `"Speed is just how far you went"` | MISCONCEPTION | COUNTEREXAMPLE |
| `"I don't know where to start"` | STUCK | HINT |
| `"240 divided by 3 is 80 km/h"` | CORRECT | ACKNOWLEDGE |
| `"What's the weather today?"` | OFF_TOPIC | REDIRECT |
| `"Can you give me a harder one?"` | CHALLENGE_READY | CHALLENGE |

---

## 5. Module: Policy Engine (VT-07)

**File:** `policy.py`  
**No I/O. No async. No LLM calls. Pure Python conditionals.**  
Every rule is independently unit-testable.

### 5.1 Constraint Pipeline

Rules run in this order. Each rule takes `(output, state)` and returns `(output, override_fired: bool)`.

```python
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
```

### 5.2 Stage 1 — Validate Output

```python
VALID_CLASSIFICATIONS = {
    "CORRECT", "PARTIALLY_CORRECT", "MISCONCEPTION",
    "STUCK", "CHALLENGE_READY", "OFF_TOPIC",
}
VALID_STRATEGIES = {
    "ACKNOWLEDGE", "PROBE", "HINT", "COUNTEREXAMPLE",
    "CORRECTION", "SIMPLER_SUBPROBLEM", "CHALLENGE",
    "REDIRECT", "NEXT_PROBLEM",
}

def rule_validate_output(
    output: LLMReasoningOutput | None,
    state: LearnerState,
) -> tuple[LLMReasoningOutput, bool]:
    if output is None:
        return _fallback(state, "parse_failure"), True

    if output.classification not in VALID_CLASSIFICATIONS:
        return _fallback(state, "invalid_classification"), True

    if output.strategy not in VALID_STRATEGIES:
        return _fallback(state, "invalid_strategy"), True

    if output.response and len(output.response.split()) > 50:
        output.response = _trim_to_sentence(output.response)

    return output, False


def _fallback(state: LearnerState, reason: str) -> LLMReasoningOutput:
    strategy = "HINT" if state.attempt_count <= 2 else "SIMPLER_SUBPROBLEM"
    return LLMReasoningOutput(
        classification="STUCK",
        strategy=strategy,
        reasoning=f"policy_fallback:{reason}",
        response=None,
    )


def _trim_to_sentence(text: str) -> str:
    """Return text up to and including the first sentence boundary."""
    for i, ch in enumerate(text):
        if ch in ".?!" and i < len(text) - 1:
            return text[: i + 1]
    return text  # no boundary found — return as-is
```

### 5.3 Stage 2 — Constraint Rules

**Rule 1 — No correction on first attempt**

```python
def rule_no_correction_on_first(
    output: LLMReasoningOutput, state: LearnerState
) -> tuple[LLMReasoningOutput, bool]:
    if output.strategy == "CORRECTION" and state.attempt_count <= 1:
        output.strategy = "COUNTEREXAMPLE"
        return output, True
    return output, False
```

*Why:* Direct correction on a first attempt short-circuits self-correction. The learner needs a second frame before being told they're wrong.

---

**Rule 2 — No direct answer**

```python
def rule_no_direct_answer(
    output: LLMReasoningOutput, state: LearnerState
) -> tuple[LLMReasoningOutput, bool]:
    if (
        output.strategy == "NEXT_PROBLEM"
        and output.classification not in ("CORRECT", "CHALLENGE_READY")
    ):
        output.strategy = "HINT"
        return output, True
    return output, False
```

*Why:* Guards against the LLM advancing past an unresolved misconception.

---

**Rule 3 — Hesitation softening**

```python
SOFTEN_MAP = {
    "PROBE": "HINT",
    "CHALLENGE": "PROBE",
    "CORRECTION": "HINT",
}

def rule_hesitation_softening(
    output: LLMReasoningOutput, state: LearnerState
) -> tuple[LLMReasoningOutput, bool]:
    if state.hesitation_score < 0.6:
        return output, False

    if output.strategy in SOFTEN_MAP:
        output.strategy = SOFTEN_MAP[output.strategy]
        output.soften_flag = True   # signals adaptation context
        return output, True

    # Even if strategy doesn't change, flag the softening for tone
    output.soften_flag = True
    return output, False
```

*Why:* High hesitation means the learner is struggling regardless of whether the answer direction is right. Pushing hard here causes disengagement.  
`soften_flag` is the **only** bridge between policy and adaptation. It flows one way: policy sets it, adaptation reads it.

---

**Rule 4 — STUCK escalation**

```python
def rule_stuck_escalation(
    output: LLMReasoningOutput, state: LearnerState
) -> tuple[LLMReasoningOutput, bool]:
    if output.classification != "STUCK":
        return output, False

    overridden = False
    if state.attempt_count >= 3:
        output.strategy = "SIMPLER_SUBPROBLEM"
        overridden = True

    if state.attempt_count >= 5:
        output.flag_for_review = True  # log for human review

    return output, overridden
```

*Why:* The LLM will often return HINT every time a learner is stuck. Policy is what ensures help escalates deterministically after repeated failures.

---

**Rule 5 — Challenge gate**

```python
CHALLENGE_MASTERY_THRESHOLD = 0.85

def rule_challenge_gate(
    output: LLMReasoningOutput, state: LearnerState
) -> tuple[LLMReasoningOutput, bool]:
    if output.strategy != "CHALLENGE":
        return output, False

    problem = problem_bank.get(state.current_problem_id)
    mastery = state.mastery_by_skill.get(problem.skill_code, 0.0)

    if mastery < CHALLENGE_MASTERY_THRESHOLD:
        output.strategy = "PROBE"
        return output, True

    return output, False
```

*Why:* The LLM can be optimistic about learner readiness. 0.85 is the gate: high enough to be meaningful, not so high that a single slip blocks progression.

---

**Rule 6 — Off-topic redirect**

```python
def rule_off_topic_redirect(
    output: LLMReasoningOutput, state: LearnerState
) -> tuple[LLMReasoningOutput, bool]:
    if output.classification != "OFF_TOPIC":
        return output, False

    output.strategy = "REDIRECT"
    output.response = None  # response generator uses template, not LLM draft
    return output, True
```

*Why:* Off-topic is the one case where the response generator uses a hard-coded template. We do not want the LLM to generate a creative redirect that might accidentally engage with off-topic content.

---

**Rule 7 — Correction cycle limit**

```python
CORRECTION_CYCLE_LIMIT = 5

def rule_correction_cycle_limit(
    output: LLMReasoningOutput, state: LearnerState
) -> tuple[LLMReasoningOutput, bool]:
    if state.correction_cycle_count < CORRECTION_CYCLE_LIMIT:
        return output, False

    output.strategy = "SIMPLER_SUBPROBLEM"
    output.soften_flag = True
    output.flag_for_review = True
    return output, True
```

*Why:* Five consecutive turns without progression means the current problem is wrong for this learner. Escalate and flag.

---

### 5.4 Constraint Matrix (Complete)

Every `(classification, strategy)` the LLM can return, and what policy emits:

| Classification | LLM strategy | Condition | Policy override | Final strategy |
|---|---|---|---|---|
| CORRECT | ACKNOWLEDGE | any | none | ACKNOWLEDGE |
| CORRECT | NEXT_PROBLEM | any | none | NEXT_PROBLEM |
| PARTIALLY_CORRECT | PROBE | hesitation < 0.6 | none | PROBE |
| PARTIALLY_CORRECT | PROBE | hesitation ≥ 0.6 | Rule 3 soften | HINT |
| MISCONCEPTION | COUNTEREXAMPLE | any | none | COUNTEREXAMPLE |
| MISCONCEPTION | CORRECTION | attempt ≤ 1 | Rule 1 | COUNTEREXAMPLE |
| MISCONCEPTION | CORRECTION | attempt ≥ 2 | none | CORRECTION |
| STUCK | HINT | attempt 1–2 | none | HINT |
| STUCK | HINT | attempt ≥ 3 | Rule 4 | SIMPLER_SUBPROBLEM |
| CHALLENGE_READY | CHALLENGE | mastery ≥ 0.85 | none | CHALLENGE |
| CHALLENGE_READY | CHALLENGE | mastery < 0.85 | Rule 5 | PROBE |
| OFF_TOPIC | any | any | Rule 6 (hard) | REDIRECT |
| any | NEXT_PROBLEM | classification ∉ {CORRECT, CHALLENGE_READY} | Rule 2 | HINT |
| parse failure | — | any | Rule validate | HINT or SIMPLER_SUBPROBLEM |

---

### 5.5 Entrypoint: enforce()

```python
def enforce(
    raw_output: LLMReasoningOutput | None,
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
```

---

## 6. Module: Learner State and BKT (VT-08)

**File:** `state.py`

### 6.1 State Updates After Each Turn

Called by `__init__.py` after the policy engine emits a decision and the response has been sent.

```python
def update_after_turn(
    state: LearnerState,
    decision: OrchestratorDecision,
    utterance: str,
    tutor_response: str,
) -> LearnerState:
    """Return a new LearnerState. Do not mutate the original."""
    import copy
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
```

### 6.2 BKT Update Function

```python
# BKT parameters — fixed for MVP; will be per-skill in Phase 2
P_TRANSIT = 0.10   # P(learn | not known) per attempt
P_SLIP    = 0.10   # P(wrong | known)
P_GUESS   = 0.20   # P(right | not known)

def bkt_update(p_know: float, is_correct: bool) -> float:
    """
    Update P(Learned) after observing a correct or incorrect response.
    Returns the new p_know (clamped to [0.01, 0.99]).
    """
    if is_correct:
        p_obs_given_know    = 1.0 - P_SLIP
        p_obs_given_not     = P_GUESS
    else:
        p_obs_given_know    = P_SLIP
        p_obs_given_not     = 1.0 - P_GUESS

    # Posterior via Bayes
    numerator   = p_obs_given_know * p_know
    denominator = numerator + p_obs_given_not * (1.0 - p_know)
    p_know_posterior = numerator / denominator

    # Apply learning transition
    p_know_new = p_know_posterior + (1.0 - p_know_posterior) * P_TRANSIT

    return max(0.01, min(0.99, p_know_new))
```

### 6.3 Difficulty Selection

Called when the current problem is completed (strategy = NEXT_PROBLEM).

```python
MASTERY_ADVANCE_THRESHOLD = 0.95   # advance to harder difficulty
MASTERY_RETREAT_THRESHOLD = 0.20   # retreat to easier difficulty (after 3 attempts)
RETREAT_ATTEMPT_MINIMUM   = 3

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
```

### 6.4 SQLite Persistence

```python
import sqlite3
from pathlib import Path

DB_PATH = Path("tutor_sessions.db")

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
    import json
    from dataclasses import asdict
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO learner_states (session_id, state_json, updated_at)
        VALUES (?, ?, datetime('now'))
    """, (state.session_id, json.dumps(asdict(state), default=str)))
    conn.commit()
    conn.close()
```

---

## 7. Module: Trace Logger

**File:** `trace.py`  
**Every turn writes one row. This is not optional logging — it is the primary debugging tool.**

```python
import sqlite3
import json
from pathlib import Path
from models import OrchestratorTrace

TRACE_DB_PATH = Path("orchestrator_traces.db")

def init_trace_db() -> None:
    conn = sqlite3.connect(TRACE_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            turn_index INTEGER,
            utterance TEXT,
            stt_confidence REAL,
            hesitation_score REAL,
            llm_classification TEXT,
            llm_strategy TEXT,
            policy_override INTEGER,
            final_strategy TEXT,
            response TEXT,
            adaptation_applied TEXT,
            latency_llm_ms INTEGER,
            latency_tts_ms INTEGER,
            latency_e2e_ms INTEGER,
            flag_for_review INTEGER,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def write(trace: OrchestratorTrace) -> None:
    conn = sqlite3.connect(TRACE_DB_PATH)
    conn.execute("""
        INSERT INTO traces VALUES (
            NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, (
        trace.session_id,
        trace.turn_index,
        trace.utterance,
        trace.stt_confidence,
        trace.hesitation_score,
        trace.llm_classification,
        trace.llm_strategy,
        int(trace.policy_override),
        trace.final_strategy,
        trace.response,
        json.dumps(trace.adaptation_applied),
        trace.latency_llm_ms,
        trace.latency_tts_ms,
        trace.latency_e2e_ms,
        int(getattr(trace, "flag_for_review", False)),
        str(trace.timestamp),
    ))
    conn.commit()
    conn.close()
```

**Debugging query to answer "why did the tutor do that?":**

```sql
SELECT
    turn_index,
    utterance,
    llm_classification,
    llm_strategy,
    policy_override,
    final_strategy,
    response,
    latency_e2e_ms
FROM traces
WHERE session_id = '<your_session_id>'
ORDER BY turn_index;
```

---

## 8. Public Entry Point

**File:** `__init__.py`  
This is the only function Varshini's Turn Manager calls.

```python
import time
from datetime import datetime
from models import LearnerState, OrchestratorTrace, TutorResponse
from . import llm, policy, state as state_module, trace, response as resp_module
from .problem_bank import get as get_problem

# In-memory session store (MVP); flush to SQLite on turn end
_SESSIONS: dict[str, LearnerState] = {}

async def process_turn(
    utterance: str,
    session_id: str,
    stt_confidence: float = 1.0,
) -> TutorResponse:
    """
    The only public function. Called by Turn Manager on validated utterance.
    Returns TutorResponse { text: str, strategy: str, updated_state: LearnerState }.
    """
    t_start = time.monotonic()

    # 1. Load state
    learner_state = _SESSIONS[session_id]
    problem = get_problem(learner_state.current_problem_id)

    # 2. LLM reasoning
    llm_output, latency_llm = await llm.reason(utterance, learner_state, problem)

    # 3. Policy enforcement
    decision = policy.enforce(llm_output, learner_state)

    # 4. Response generation (assembles prompt, calls TTS streamer)
    response_text, latency_tts = await resp_module.generate(decision, problem)

    # 5. State update
    updated_state = state_module.update_after_turn(
        learner_state, decision, utterance, response_text
    )
    _SESSIONS[session_id] = updated_state
    state_module.flush_state(updated_state)   # async-safe: SQLite write ~1 ms

    # 6. Trace log
    t_end = time.monotonic()
    trace.write(OrchestratorTrace(
        session_id=session_id,
        turn_index=updated_state.attempt_count,
        utterance=utterance,
        stt_confidence=stt_confidence,
        hesitation_score=learner_state.hesitation_score,
        llm_classification=llm_output.classification if llm_output else "STUCK",
        llm_strategy=llm_output.strategy if llm_output else "HINT",
        policy_override=decision.policy_override,
        final_strategy=decision.final_strategy,
        response=response_text,
        adaptation_applied=vars(decision.adaptation_context),
        latency_llm_ms=latency_llm,
        latency_tts_ms=latency_tts,
        latency_e2e_ms=int((t_end - t_start) * 1000),
        timestamp=datetime.utcnow(),
    ))

    return TutorResponse(
        text=response_text,
        strategy=decision.final_strategy,
        updated_state=updated_state,
    )
```

---

## 9. Exception Paths

### 9.1 Silence Timeout

The Turn Manager synthesises a virtual utterance and calls `process_turn` with it. The orchestrator does not need special handling — Rule 4 handles STUCK escalation normally.

```python
# In Turn Manager (Varshini's code) — not in orchestrator
async def on_silence_timeout(session_id: str):
    await orchestrator.process_turn(
        utterance="__silence_timeout__",
        session_id=session_id,
        stt_confidence=1.0,
    )
```

In the trace, `utterance = "__silence_timeout__"` makes these turns filterable separately.

### 9.2 LLM API Failure

`llm.reason()` catches all exceptions and returns `(None, latency_ms)`. Policy engine's `rule_validate_output` handles `None` input and emits a safe fallback. **The turn always completes** — a failed LLM call produces a HINT or SIMPLER_SUBPROBLEM, not an error shown to the learner.

### 9.3 Off-Topic Hard Override

`rule_off_topic_redirect` sets `response_draft = None`. The response generator detects `None` and uses this template instead of calling Claude:

```python
REDIRECT_TEMPLATE = (
    "Let's stay focused on our problem for now — "
    "we were working on {problem_short}. Where were we?"
)
```

### 9.4 Session Not Found

If `session_id` is not in `_SESSIONS`, `process_turn` raises `SessionNotFoundError`. The WebSocket handler catches this and sends an error control message to the client. This should not happen in normal operation — session creation is a separate init step.

---

## 10. Unit Test Checklist

Write these tests **before** wiring modules together. Each file has its own test file.

### test_policy.py

| Test | Input | Expected final_strategy | Override? |
|---|---|---|---|
| correction blocked on attempt 1 | classification=MISCONCEPTION, strategy=CORRECTION, attempt=1 | COUNTEREXAMPLE | True |
| correction allowed on attempt 2 | classification=MISCONCEPTION, strategy=CORRECTION, attempt=2 | CORRECTION | False |
| NEXT_PROBLEM blocked on wrong classification | classification=STUCK, strategy=NEXT_PROBLEM | HINT | True |
| hesitation softens PROBE | strategy=PROBE, hesitation=0.8 | HINT | True |
| hesitation does not fire below threshold | strategy=PROBE, hesitation=0.4 | PROBE | False |
| STUCK escalates at attempt 3 | classification=STUCK, attempt=3 | SIMPLER_SUBPROBLEM | True |
| STUCK does not escalate at attempt 2 | classification=STUCK, attempt=2 | HINT | False |
| challenge blocked below 0.85 mastery | strategy=CHALLENGE, mastery=0.7 | PROBE | True |
| challenge allowed at 0.85+ mastery | strategy=CHALLENGE, mastery=0.87 | CHALLENGE | False |
| off-topic hard override | classification=OFF_TOPIC, strategy=PROBE | REDIRECT | True |
| correction cycle limit fires at 5 | correction_cycle_count=5 | SIMPLER_SUBPROBLEM | True |
| parse failure fallback | raw_output=None, attempt=1 | HINT | True |
| parse failure escalates | raw_output=None, attempt=4 | SIMPLER_SUBPROBLEM | True |

### test_state.py

| Test | Scenario | Expected |
|---|---|---|
| BKT updates upward on correct | p_know=0.5, is_correct=True | p_know > 0.5 |
| BKT updates downward on incorrect | p_know=0.7, is_correct=False | p_know < 0.7 |
| BKT never reaches 0 or 1 | extremes | clamped to [0.01, 0.99] |
| Difficulty advances at 0.95 | mastery=0.96 | level advances |
| Difficulty retreats at 0.20 after 3 attempts | mastery=0.15, attempt=3 | level retreats |
| Difficulty stays when mastery is mid-range | mastery=0.5 | level unchanged |
| correction_cycle_count resets on CORRECT | strategy=ACKNOWLEDGE | count = 0 |
| correction_cycle_count increments otherwise | strategy=HINT | count += 1 |
| last_3_turns keeps max 6 total entries | 8 turns appended | len = 6 |

---

## 11. Integration Contract with Varshini's Pipeline

This is the only thing Varshini needs from this package.

### What Varshini calls

```python
from orchestrator import process_turn, init_session

# On new session start (called once)
await init_session(session_id, topic, language, level)

# On each validated utterance (called every turn)
response = await process_turn(
    utterance="I think you divide 240 by 3?",
    session_id=session_id,
    stt_confidence=0.91,
)
# response.text     → str  — send this to ElevenLabs TTS
# response.strategy → str  — for UI state (e.g. show "thinking" indicator)
```

### What the orchestrator needs from Varshini before it's called

```python
# LearnerState.hesitation_score must be set before process_turn is called.
# Varshini's Turn Manager computes this from AssemblyAI word-timing events
# and sets it on the session state before handing off.
# The orchestrator reads state.hesitation_score — it does not compute it.
```

### What Varshini never touches inside this package

- `llm.py`, `policy.py`, `state.py`, `response.py`, `trace.py`
- `problems.json`
- The SQLite databases

The boundary is `process_turn()`. Everything inside it is Vaasini's domain.

---

*Document end.*  
*This supersedes the architecture document's Section 2c (Tutor Orchestrator Design) for implementation purposes.*  
*Re-read after VT-08 is complete and before VT-10 integration begins.*
