"""
Minimal FastAPI app exposing a single WebSocket endpoint that proxies
client audio to AssemblyAI's real-time streaming API and relays
transcripts back.

Run with:
    uvicorn app.main:app --reload --port 8000
"""

import os
import sys
import uuid

# Repo root is two levels up from backend/app/ — needed to import orchestrator/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket

from app.assemblyai_stream import run_bridge
from app.tts import send_tutor_turn
from orchestrator import init_session, process_turn
from orchestrator.intake import handle as intake_handle
from orchestrator.models import SessionNotFoundError

load_dotenv()

app = FastAPI(title="Voice First Tutor - Audio Pipeline MVP")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.websocket("/ws/session")
async def ws_session(websocket: WebSocket, lang: str = "en") -> None:
    await websocket.accept()
    session_id = str(uuid.uuid4())
    is_first_turn = [True]

    async def on_turn(turn_text: str) -> None:
        if not turn_text.strip():
            return

        if is_first_turn[0]:
            is_first_turn[0] = False
            topic, level, problem_id, opening = await intake_handle(turn_text, language=lang)
            await init_session(
                session_id,
                topic=topic,
                language=lang,
                level=level,
                problem_id=problem_id,
            )
            await send_tutor_turn(websocket, opening)
        else:
            try:
                response = await process_turn(turn_text, session_id)
                await send_tutor_turn(websocket, response.text)
            except SessionNotFoundError:
                await send_tutor_turn(
                    websocket,
                    "Something went wrong with your session — please refresh and try again.",
                )

    await run_bridge(websocket, on_turn=on_turn)
