# QE scratch artifacts

These files are ad-hoc QE artifacts for manually exercising the
`/ws/session` audio pipeline (see `backend/README.md` for the protocol).
They are **not** part of the application and are not imported by any
app code.

- `sample1.wav`, `sample2.wav` — 16kHz mono 16-bit PCM WAV files
  generated locally with macOS `say` + `afconvert` (no network, no
  mic). Ground-truth transcripts:
  - `sample1.wav`: "Hello, I'm ready to start my math tutoring session today."
  - `sample2.wav`: "A train travels two hundred forty kilometers in three hours. What is its average speed?"
- `qe_test_client.py` — a standalone WebSocket test client. Streams a
  WAV file's PCM16 payload to `/ws/session` in ~100ms chunks with
  real-time pacing, collects all JSON messages received, sends
  `{"type": "terminate"}` at the end, and prints a trace/summary
  (Begin received, turn count, final transcript, Termination
  received, errors).

  Usage:
  ```bash
  source ../.venv/bin/activate
  python qe_test_client.py sample1.wav --url ws://localhost:8000/ws/session
  python qe_test_client.py --no-audio --label empty-terminate
  ```

No API keys or secrets are stored in this directory.
