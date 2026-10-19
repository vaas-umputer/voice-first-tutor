"""All dataclasses used across the orchestrator package. No logic lives here."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class Turn:
    role: Literal["tutor", "learner"]
    text: str
    timestamp: datetime


@dataclass
class LearnerState:
    session_id: str
    topic: str  # e.g. "math.ratio.speed_distance_time"
    language: str  # BCP-47: "en", "hi", "ta"
    level: Literal["easy", "medium", "hard"]
    current_problem_id: str
    attempt_count: int  # resets on new problem
    correction_cycle_count: int  # resets on CORRECT / CHALLENGE_READY
    mastery_by_skill: dict = field(default_factory=dict)  # skill_code -> p_know (0.0-1.0)
    misconceptions: list = field(default_factory=list)  # accumulated this session
    hesitation_score: float = 0.0  # 0.0-1.0; set by Turn Manager before handoff
    last_3_turns: list = field(default_factory=list)  # rolling window of Turn


@dataclass
class Problem:
    id: str  # e.g. "prob_007"
    text: str  # the question shown/spoken to the learner
    skill_code: str  # e.g. "math.ratio.speed_distance_time"
    difficulty: Literal["easy", "medium", "hard"]
    worked_solution: str  # NEVER sent to learner; injected into LLM prompt only
    concepts: list = field(default_factory=list)  # e.g. ["division", "ratio", "units"]


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
    reasoning: str  # 1 sentence, internal only - never reaches learner
    response: Optional[str] = None  # raw draft <= 40 words, ends with "?"; None on some overrides
    # The two fields below are not part of the documented LLM JSON payload, but policy.py
    # (Rules 3, 4, 7) sets them on the output object as it flows through the pipeline, and
    # enforce() reads them back via getattr — declared here so they have a home on the dataclass.
    soften_flag: bool = False
    flag_for_review: bool = False


@dataclass
class AdaptationContext:
    language: str  # BCP-47 - drives language directive
    pace: Literal["slow", "normal", "fast"]  # derived from hesitation_score
    style: Literal["concise", "detailed"]  # derived from attempt_count
    soften: bool  # set True by Rule 3 (hesitation)

    @classmethod
    def from_state(cls, state: LearnerState, soften: bool = False) -> "AdaptationContext":
        pace = "slow" if state.hesitation_score > 0.6 else ("fast" if state.hesitation_score < 0.2 else "normal")
        style = "detailed" if state.attempt_count >= 3 else "concise"
        return cls(
            language=state.language,
            pace=pace,
            style=style,
            soften=soften,
        )


@dataclass
class OrchestratorDecision:
    final_strategy: str  # one of the strategy enum values
    policy_override: bool  # True if any constraint rule fired
    response_draft: Optional[str]  # None -> response generator builds from strategy template
    adaptation_context: AdaptationContext
    soften_flag: bool  # True -> prepend effort acknowledgment
    flag_for_review: bool  # True -> log for human review (correction_cycle >= 5)
    problem_id: str
    session_id: str


@dataclass
class OrchestratorTrace:
    session_id: str
    turn_index: int
    utterance: str  # "__silence_timeout__" on timeout path
    stt_confidence: float
    hesitation_score: float
    llm_classification: str
    llm_strategy: str
    policy_override: bool
    final_strategy: str
    response: str
    adaptation_applied: dict  # serialised AdaptationContext
    latency_llm_ms: int
    latency_tts_ms: int  # filled by response.py after TTS call
    latency_e2e_ms: int  # filled by __init__.py at turn end
    timestamp: datetime
    flag_for_review: bool = False


@dataclass
class TutorResponse:
    """Returned by process_turn() to the Turn Manager. Not fully spec'd in the doc;
    inferred from section 8's usage (response.text / response.strategy) and section 11."""
    text: str
    strategy: str
    updated_state: LearnerState


class SessionNotFoundError(Exception):
    """Raised by process_turn() when session_id is not in _SESSIONS (see section 9.4)."""
