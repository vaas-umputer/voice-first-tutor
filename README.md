
A voice-native AI math tutor. The learner speaks; audio streams in real time to AssemblyAI's v3 STT engine; final turn transcripts go to a Socratic tutoring orchestrator powered by Claude; the tutor's response is spoken back via browser TTS. No typing required.

---

## Architecture

```
Browser mic (PCM16LE 16 kHz)
    │  binary WebSocket frames
    ▼
FastAPI  /ws/session?lang=en|hi          ← backend/app/main.py
    │  websockets proxy
    ▼
AssemblyAI v3 Streaming STT              ← universal-3-5-pro
    │  Begin / Turn (partial+final) / Termination
    ▼
on_turn hook  (fires on end_of_turn=True)
    │
    ├─ first turn ──▶  orchestrator/intake.py  (topic + level detection)
    │                        │
    │                        ▼
    │                  init_session(session_id, topic, language, level)
    │
    └─ later turns ─▶  process_turn(utterance, session_id)
                               │
                               ▼
                         tutor_turn JSON  →  browser speechSynthesis
```

| File | Role |
|---|---|
| `backend/app/assemblyai_stream.py` | AssemblyAI v3 WebSocket bridge; `on_turn` hook |
| `backend/app/main.py` | FastAPI app; orchestrator wiring; two-phase session init |
| `backend/app/tts.py` | Sends `tutor_turn` JSON to the browser |
| `orchestrator/__init__.py` | Public API: `init_session`, `process_turn` |
| `orchestrator/intake.py` | First-message topic/level detection; Hindi/Hinglish routing |
| `orchestrator/models.py` | `LearnerState`, `TutorResponse`, `SessionNotFoundError` |
| `backend/scratch/test_mic.html` | Live mic test page (no React, `file://`-compatible) |

---

## Running locally

**Requirements:** Python 3.11+, AssemblyAI API key, optionally Anthropic API key.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```
ASSEMBLYAI_API_KEY=<your key>
ANTHROPIC_API_KEY=<optional — enables Claude-powered intake and tutoring>
```

```bash
uvicorn app.main:app --reload --port 8000
```

Open `backend/scratch/test_mic.html` directly in Chrome (no server needed). Pick a language, hit **Start session**, speak.

**LLM backend** (env var `TUTOR_LLM_BACKEND`):

| Value | Behaviour |
|---|---|
| *(unset)* + `ANTHROPIC_API_KEY` set | Claude via Anthropic API |
| `anthropic` | Claude (explicit) |
| `ollama` | Local Ollama; set `OLLAMA_MODEL` (default: `llama3.2`) |
| *(unset, no key)* | Keyword-heuristic mock — no API needed |

---

## What is built

- **Real-time audio pipeline** — browser mic → PCM16LE frames → FastAPI WebSocket → AssemblyAI v3 streaming; partial and final transcripts relayed back to the client
- **Bridge bug fixes** — asyncio `FIRST_COMPLETED` race condition fixed with a 5 s drain window so final-turn transcripts are never dropped; bad API key detected from the first JSON message type rather than HTTP status (AssemblyAI v3 completes the WS handshake before rejecting)
- **Orchestrator integration** — two-phase session init: `intake.handle` on turn 1, `process_turn` on subsequent turns; `SessionNotFoundError` handled gracefully
- **Multilingual routing** — `?lang=hi` flows end-to-end: browser → FastAPI → orchestrator → TTS `lang` tag (`hi-IN`); `universal-3-5-pro` handles Hindi/Hinglish at the STT layer natively
- **Live mic test page** — `ScriptProcessorNode`-based (CORS-free, `file://`-compatible); language selector; client-side barge-in; partial-turn display

---

## What is deferred

| Feature | Notes |
|---|---|
| Hesitation / silence detection | Proactive prompting when the learner goes quiet |
| Server-side barge-in | Currently client-only (`speechSynthesis.cancel()`) |
| Adaptive difficulty | Escalate/de-escalate based on mastery signals from the orchestrator |
| Session persistence | Resume across page reloads; DB-backed `LearnerState` |
| Additional languages | Tamil, Telugu — routing stubs in `orchestrator/response.py` |
| Problem bank expansion | Currently only `math.ratio.speed_distance_time` |
| Production frontend | Replace `test_mic.html` with a proper UI |
