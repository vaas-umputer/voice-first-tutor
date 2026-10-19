"""
Interactive tutor demo — learner reaches out first.

  python3 orchestrator/demo.py                           # mock backend
  TUTOR_LLM_BACKEND=ollama python3 orchestrator/demo.py  # local Ollama
"""

import asyncio
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator import init_session, process_turn
from orchestrator import state as state_module
from orchestrator import trace as trace_module
from orchestrator.intake import handle as intake_handle

BACKEND = os.environ.get("TUTOR_LLM_BACKEND", "mock")


async def main():
    state_module.init_db()
    trace_module.init_trace_db()

    print(f"\n  [Backend: {BACKEND}]")
    print(f"  Priya: Hi! I'm Priya, your math tutor. What are you working on today?\n")

    # --- Learner speaks first ---
    try:
        first_message = input("  You: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Bye!")
        return

    if not first_message or first_message.lower() in ("quit", "exit", "q"):
        print("  Bye!")
        return

    # --- Intake: figure out topic/level from what they said ---
    topic, level, problem_id, opening = await intake_handle(first_message)

    session_id = "demo-session-001"
    await init_session(
        session_id=session_id,
        topic=topic,
        language="en",
        level=level,
        problem_id=problem_id,
    )

    print(f"\n  Priya: {opening}\n")

    # --- Tutoring loop ---
    while True:
        try:
            utterance = input("  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Bye!")
            break

        if not utterance:
            continue
        if utterance.lower() in ("quit", "exit", "q"):
            print("  Bye!")
            break

        response = await process_turn(
            utterance=utterance,
            session_id=session_id,
            stt_confidence=1.0,
        )

        print(f"\n  Priya: {response.text}")

        conn = sqlite3.connect(trace_module.TRACE_DB_PATH)
        row = conn.execute(
            "SELECT llm_classification, final_strategy, policy_override, "
            "latency_llm_ms, latency_tts_ms, latency_e2e_ms FROM traces "
            "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        conn.close()

        override = " [policy override]" if row[2] else ""
        print(
            f"  \033[2m[{row[0]} → {row[1]}{override} | "
            f"llm {row[3]}ms  resp {row[4]}ms  e2e {row[5]}ms]\033[0m\n"
        )


if __name__ == "__main__":
    asyncio.run(main())
