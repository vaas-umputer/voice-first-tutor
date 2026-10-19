"""Writes OrchestratorTrace to SQLite per turn. See section 7 of the impl spec."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import OrchestratorTrace

TRACE_DB_PATH = Path(__file__).parent / "orchestrator_traces.db"


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
