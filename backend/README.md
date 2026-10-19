# Voice First Tutor — Audio Pipeline MVP (backend)

This is a minimal first cut of the real-time audio pipeline: it proves
client audio -> server -> AssemblyAI live transcription -> client, and
nothing else. No turn-detection tuning, no hesitation scoring, no LLM
orchestration, no TTS — that all comes later.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set ASSEMBLYAI_API_KEY=<your real key>
```

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

The server exposes:

- `GET /health` — basic liveness check
- `WS /ws/session` — the audio pipeline endpoint

## WebSocket protocol (`/ws/session`)

### Client sends

- **Binary frames**: raw PCM16LE audio, 16kHz, mono. Send audio chunks as
  they become available (e.g. every 50-200ms of audio).
- **Optional JSON control message** to end the session cleanly:
  ```json
  {"type": "terminate"}
  ```
  Always send this (or simply disconnect) when you're done — the server
  forwards a `Terminate` message to AssemblyAI either way, but sending it
  explicitly ends the upstream session immediately instead of waiting on
  a disconnect timeout. AssemblyAI bills by session duration, so don't
  leave sessions open longer than necessary.

### Client receives

JSON messages, passed through from AssemblyAI verbatim, plus this
server's own error shape:

- `{"type": "Begin", ...}` — sent once, right after the connection to
  AssemblyAI is established.
- `{"type": "Turn", "transcript": "...", "end_of_turn": bool, "turn_is_formatted": bool, ...}` —
  sent continuously as speech is transcribed.
- `{"type": "Termination", ...}` — sent when the session ends.
- `{"type": "error", "detail": "..."}` — this server's own error
  reporting, for cases like a missing/invalid API key or an unexpected
  failure in the pipeline. Not part of AssemblyAI's protocol.

If AssemblyAI rejects the connection (e.g. bad API key), the server
sends an `error` message and closes the client socket with code `1008`
instead of hanging silently.

## Notes

- The outbound connection to AssemblyAI uses the `websockets` async
  client under the hood; the inbound client connection uses FastAPI's
  native WebSocket support.
- This module is intentionally just plumbing: `app/main.py` wires up the
  endpoint, and `app/assemblyai_stream.py` holds the bridging logic. No
  session managers, turn managers, or tutoring logic live here.
