"""Public entry point. process_turn() and init_session() are the only functions
outside code should call. See section 8 and section 11 of the impl spec."""

from __future__ import annotations

import time
from datetime import datetime

from . import llm, policy
from . import state as state_module
from . import trace
from . import response as resp_module
from .models import LearnerState, OrchestratorTrace, SessionNotFoundError, TutorResponse
from .problem_bank import get as get_problem, select_for_level

# In-memory session store (MVP); flushed to SQLite on turn end
_SESSIONS = {}

_dbs_initialized = False


def _ensure_dbs() -> None:
    global _dbs_initialized
    if not _dbs_initialized:
        state_module.init_db()
        trace.init_trace_db()
        _dbs_initialized = True


async def init_session(
    session_id: str,
    topic: str,
    language: str,
    level: str,
    problem_id: str = None,
) -> LearnerState:
    """Create a fresh LearnerState for a new session. If problem_id is given (e.g.
    from the intake module after the learner's first message), use it directly;
    otherwise select a random problem at the given level."""
    _ensure_dbs()

    if problem_id:
        starting_problem = get_problem(problem_id)
    else:
        starting_problem = select_for_level(level)

    state = LearnerState(
        session_id=session_id,
        topic=topic,
        language=language,
        level=level,
        current_problem_id=starting_problem.id,
        attempt_count=0,
        correction_cycle_count=0,
        mastery_by_skill={},
        misconceptions=[],
        hesitation_score=0.0,
        last_3_turns=[],
    )
    _SESSIONS[session_id] = state
    state_module.flush_state(state)
    return state


async def process_turn(
    utterance: str,
    session_id: str,
    stt_confidence: float = 1.0,
) -> TutorResponse:
    """
    The only public function. Called by Turn Manager on validated utterance.
    Returns TutorResponse { text: str, strategy: str, updated_state: LearnerState }.
    """
    _ensure_dbs()
    t_start = time.monotonic()

    # 1. Load state
    if session_id not in _SESSIONS:
        raise SessionNotFoundError(session_id)
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
    state_module.flush_state(updated_state)  # async-safe: SQLite write ~1 ms

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
        flag_for_review=decision.flag_for_review,
        timestamp=datetime.utcnow(),
    ))

    return TutorResponse(
        text=response_text,
        strategy=decision.final_strategy,
        updated_state=updated_state,
    )
