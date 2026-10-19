# Voice-First AI Tutoring System — Technical Architecture Document

**Version:** 1.0  
**Date:** 2026-09-06  
**Status:** Internal Draft — Development Team  
**Hackathon Target:** AssemblyAI Voice Agent Hackathon 2026

---

## Table of Contents

1. [Technology Comparison Matrices](#1-technology-comparison-matrices)
2. [MVP Architecture Blueprint](#2-mvp-architecture-blueprint)
3. [Phase 2 Architecture Changes](#3-phase-2-architecture-changes)
4. [Phase 3 Architecture Changes](#4-phase-3-architecture-changes)
5. [Production Readiness Checklist](#5-production-readiness-checklist)
6. [Architecture Decision Records (ADRs)](#6-architecture-decision-records-adrs)
7. [Implementation Roadmap with Milestones](#7-implementation-roadmap-with-milestones)
8. [Risk Register](#8-risk-register)

---

## 1. Technology Comparison Matrices

### 1.1 Speech-to-Text (STT)

> **MVP is locked to AssemblyAI** per hackathon constraint. The comparison below is for Phase 2+ migration/augmentation decisions only.

| Provider | Maturity | Latency (streaming) | Cost | Multilingual / Vernacular | Ecosystem / Integration | Team Fit | Recommendation |
|---|---|---|---|---|---|---|---|
| **AssemblyAI — Universal-3.5 Pro Streaming** (MVP locked) | High — production-grade | Early partial ~750 ms; continuous partials every ~3 s; end-of-turn is punctuation-based (not fixed latency) | $0.45/hr **session duration** (billed on WS-open time, not audio sent) | 18 languages with **native code-switching in one model** — en, es, de, fr, pt, it, tr, nl, sv, no, da, fi, **hi**, vi, ar, he, ja, zh. **No Tamil or Telugu at any accuracy level.** | `wss://streaming.assemblyai.com/v3/ws`; typed `Begin`/`Turn`/`Termination` events; word-level confidence + timing | Simple WS API, great DX; official Python/JS SDKs | **USE for MVP; reassess Tamil/Telugu at Phase 2** |
| Deepgram Nova-2 | High — production-grade | ~200–400 ms (fastest in class) | $0.59/hr streaming | 30+ languages; strong Indian English | WebSocket streaming; Nova-2 outperforms on accented speech | Similar DX to AssemblyAI | **Preferred Phase 2 upgrade if AssemblyAI vernacular accuracy is insufficient** |
| OpenAI Whisper (self-hosted) | High model quality; infra burden | 1–3 s batch; not true streaming | Compute cost only (~$0.006/min on A10G) | Excellent multilingual (99 languages) | Must wrap in streaming chunking; no native WS | High infra effort | Consider only if on-prem data residency is required |
| Google STT v2 | Very High — enterprise | ~400–600 ms | $0.016/min ($0.96/hr) | 125+ languages; best-in-class Indic | gRPC streaming; tight GCP lock-in | Moderate DX | **Required for Tamil/Telugu — AssemblyAI has zero coverage, not just weaker accuracy** |
| Azure Speech | Very High — enterprise | ~400–700 ms | $1.00/hr real-time | 100+ languages; good Indic models | SDK-heavy; strong offline/edge model support | Moderate DX | Long-term option for offline packs (Phase 4) |

> **Corrected vs. v1.0 of this doc:** AssemblyAI's real-time product is now **Universal-3.5 Pro Streaming** (`speech_model: "universal-3-5-pro"`) over the **v3 WebSocket API** (`wss://streaming.assemblyai.com/v3/ws`) — the v2 endpoint (`api.assemblyai.com/v2/realtime`) and its `TranscriptEvent`/`is_final` schema are retired. Two upgrades matter for this product: (1) it's cheaper than assumed — $0.45/hr, not $0.65/hr — and (2) it natively code-switches Hindi↔English in one model, which **resolves the "no Hinglish support" gap** called out in [ADR-001](#adr-001-assemblyai-for-stt-mvp-constraint). The unresolved gap got *more* severe on closer reading: Tamil and Telugu aren't in the 18-language list at all, so Phase 2's Google STT routing for those two languages is now a hard requirement, not an accuracy upgrade.

**Decision for Phase 2:** Deepgram Nova-2 as primary with AssemblyAI as fallback for English/Hindi. Tamil and Telugu route to Google STT v2 from day one of Phase 2 (see [§3.2](#32-multilingual--vernacular-stt-strategy)) since AssemblyAI cannot serve them at any quality level.

---

### 1.2 LLM for Reasoning / Tutor Policy

| Model | Maturity | Latency (TTFT) | Cost (input/output per 1M tokens) | Multilingual | Ecosystem / Integration | Team Fit | Recommendation |
|---|---|---|---|---|---|---|---|
| **Claude claude-sonnet-4-6** | Production | ~600 ms TTFT; ~80 tok/s | $3 / $15 | Excellent — strong Hindi/Tamil reasoning | Anthropic SDK; structured output; extended thinking mode | Clean API; system prompt control | **RECOMMENDED — best reasoning + safety controls** |
| GPT-4o | Production | ~500 ms TTFT; ~100 tok/s | $2.50 / $10 | Good multilingual | OpenAI SDK; strong function calling | Ubiquitous, easy to find help | Strong alternative; slightly weaker pedagogical instruction-following vs Claude |
| Gemini 1.5 Pro | Production | ~800 ms TTFT; ~60 tok/s | $1.25 / $5 | Best-in-class multilingual | Google AI SDK; 1M context window is useful | Moderate DX | Consider for Phase 2 multilingual; not for MVP due to higher latency |
| Llama 3.3 70B (self-hosted) | Moderate — requires infra ops | ~1.2 s TTFT on A100 | ~$0.35/hr compute | Moderate multilingual | vLLM / Ollama; full control | High infra effort | Only if cost becomes untenable at scale (Phase 3+); not MVP |

**Decision:** Claude claude-sonnet-4-6 (claude-sonnet-4-6). Rationale: superior instruction-following for Socratic constrained prompts, built-in content safety layers, structured JSON output support, and extended thinking mode enables multi-step pedagogical reasoning. Keep GPT-4o as a hot fallback.

---

### 1.3 Text-to-Speech (TTS)

| Provider | Maturity | Latency (TTFB streaming) | Cost | Multilingual / Vernacular | Naturalness | Recommendation |
|---|---|---|---|---|---|---|
| **ElevenLabs** | High | ~300–500 ms streaming | $0.30/1K chars ($11/mo Starter) | 32 languages; Hindi available; accent cloning possible | Best-in-class naturalness; warm, engaging tone | **RECOMMENDED for MVP** |
| Google TTS (WaveNet/Neural2) | Very High | ~200–400 ms | $0.016/1M chars (Neural2) | 220+ languages; best Indic coverage | Good but slightly robotic vs ElevenLabs | **Phase 2 for Indic vernacular voices** |
| Azure Neural TTS | Very High | ~250–450 ms | $15/1M chars | 140+ languages; strong Hindi/Tamil neural voices | Good naturalness; enterprise-grade | Phase 2 fallback alongside Google |
| Kokoro (open-source) | Low-Moderate | ~500–900 ms (on-device) | Free (compute only) | English + limited; poor Indic | Acceptable for English; not production-ready | Phase 4 offline packs only |

**Decision:** ElevenLabs for MVP (single Hindi + English voice, no accent cloning needed at MVP). Phase 2: add Google Neural2 voices for Tamil, Telugu, Bengali, routing by detected locale. Cache TTS audio for repeated tutor phrases (hints, acknowledgments) to cut cost and latency.

---

### 1.4 Frontend Framework

| Framework | Maturity | DX / Build Speed | Performance | Audio API Support | SSR / SEO | Recommendation |
|---|---|---|---|---|---|---|
| **Next.js 14 (App Router)** | Very High | Good; App Router has learning curve | Excellent with RSC | Full browser API access in client components | Best — SSR + static | **RECOMMENDED** |
| React + Vite | Very High | Excellent DX; fastest HMR | Excellent | Full browser API access | Client-side only (needs separate SSR) | Good for pure SPA; no SSR benefit |
| SvelteKit | High | Excellent DX; smaller bundle | Best bundle size | Full browser API access | Good SSR | Not recommended — smaller talent pool for team scaling |

**Decision:** React + vite initially for fast prototyping

---

### 1.5 Backend Framework

| Framework | Maturity | Performance | WebSocket Support | Streaming | Language | Recommendation |
|---|---|---|---|---|---|---|
| **FastAPI (Python)** | Very High | High (ASGI/uvicorn); ~50K req/s | Native via Starlette WebSocket | Native async generators | Python | **RECOMMENDED** |
| Node.js / Express | Very High | High; event-loop model | Native via `ws` library | Good with streams | TypeScript | Good alternative if team is JS-only |
| Hono | Moderate-High | Excellent (edge-native) | Limited — designed for edge functions | Good | TypeScript | Over-engineered for MVP; useful at Phase 3 for edge workers |

**Decision:** FastAPI. Rationale: the reasoning pipeline (LLM calls, prompt assembly, BKT state updates) is Python-native territory. AssemblyAI's Python SDK is first-class. Async support handles concurrent WebSocket sessions cleanly. Use `uvicorn` with `gunicorn` workers in production.

---

### 1.6 Database / State Management

| Option | Phase | Maturity | Latency | Cost | Scalability | Recommendation |
|---|---|---|---|---|---|---|
| **SQLite + JSON files** | MVP | Very High | <1 ms local | Free | Single-node only | **USE for MVP — zero ops overhead** |
| **PostgreSQL + Redis** | Phase 2 | Very High | ~2–5 ms (Redis), ~5–15 ms (PG) | ~$20–50/mo managed | Excellent horizontal | **Phase 2 primary** |
| Supabase (PG + realtime) | Phase 2+ | High | ~5–20 ms | Free tier → $25/mo | Good; managed PG | **Phase 2 strong option — built-in auth + realtime** |
| PlanetScale | Phase 2+ | High | ~10–30 ms global | Free tier → $29/mo | Excellent (Vitess sharding) | Overkill until >100K sessions/day |

**Decision:** SQLite (single file, in-memory option) for hackathon MVP. Phase 2: Supabase — it bundles PostgreSQL, Row-Level Security, auth, and realtime subscriptions, reducing ops burden for a small team. Add a Redis (Upstash) layer for session state hot cache.

---

### 1.7 Deployment

| Option | Phase | DX / Ops Burden | Cold Start | Cost | Scalability | Recommendation |
|---|---|---|---|---|---|---|
| **Vercel (frontend) + Railway (backend)** | MVP | Excellent — zero config | <500 ms (Railway) | Free tier + $5–20/mo | Good to ~1K concurrent | **RECOMMENDED for MVP and Phase 2** |
| Render | MVP/Phase 2 | Very Good | ~1–2 s on free tier | Free tier + $7–25/mo | Good | Strong alternative to Railway; slightly simpler networking |
| AWS ECS + CloudFront | Phase 3+ | High ops burden | None (always-on) | $100–500+/mo | Excellent | Required at production scale (>10K daily active users) |
| GCP Cloud Run + Vertex | Phase 3+ | Moderate ops | <1 s | Pay-per-request | Excellent | Good if using Google STT/TTS deeply |

**Decision:** Vercel for Next.js frontend + Railway for FastAPI backend for MVP/Phase 2. or we can use Render for both frontend and backend - whatever suits. Both have one-command deploy from GitHub. Migrate to AWS ECS (Fargate) + RDS + ElastiCache at Phase 3 when load justifies ops investment.

---

## 2. MVP Architecture Blueprint

### 2a. Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              BROWSER CLIENT                                  │
│                                                                               │
│  ┌─────────────┐   ┌──────────────────┐   ┌────────────────────────────┐   │
│  │ Microphone  │   │  Waveform / UI   │   │  Audio Player (TTS output) │   │
│  │  (WebAudio  │   │  (partial        │   │  (barge-in interrupt       │   │
│  │   capture)  │   │   transcript)    │   │   on new speech detected)  │   │
│  └──────┬──────┘   └────────▲─────────┘   └──────────────▲────────────┘   │
│         │ PCM audio chunks   │ transcript events            │ MP3/PCM stream  │
└─────────┼───────────────────┼─────────────────────────────┼─────────────────┘
          │ WebSocket (binary) │                              │
          ▼                   │                              │
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FASTAPI WEBSOCKET SERVER                               │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         Session Manager                               │   │
│  │  - One WebSocket per learner session (opens on session start,        │   │
│  │    kept persistent — v3 bills on WS-open duration)                   │   │
│  │  - Routes audio → AssemblyAI v3 WS, receives typed Begin/Turn/       │   │
│  │    Termination events back                                            │   │
│  │  - Forwards Turn partials (end_of_turn=false) to client (UI feedback)│   │
│  └───────────────────────────┬──────────────────────────────────────────┘   │
│                               │ Turn (end_of_turn=true, turn_is_formatted)   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        Turn Manager                                   │   │
│  │  - End-of-turn: AssemblyAI's own punctuation-based detection         │   │
│  │    (min_turn_silence/max_turn_silence), confirmed by end_of_turn=true│   │
│  │  - Barge-in handler: cancel active TTS, queue new turn               │   │
│  │  - Low-confidence filter: request clarification if end_of_turn_      │   │
│  │    confidence or avg word confidence < 0.7                           │   │
│  └───────────────────────────┬──────────────────────────────────────────┘   │
│                               │ Validated utterance                           │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      Learner State Store                              │   │
│  │  - In-memory dict (MVP), persisted to SQLite on turn completion      │   │
│  │  - Holds: LearnerState (topic, level, mastery, misconceptions,       │   │
│  │           current_problem, attempt_count, session_history)           │   │
│  └───────────────────────────┬──────────────────────────────────────────┘   │
│                               │ LearnerState + utterance                      │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     Tutor Orchestrator                                │   │
│  │  ┌─────────────────────┐  ┌──────────────────────────────────────┐   │   │
│  │  │  Reasoning          │  │  Response Policy                      │   │   │
│  │  │  Classifier         │  │  - Map classification → strategy      │   │   │
│  │  │  (LLM call #1)      │  │  - Select hint/probe/counterexample   │   │   │
│  │  │  Returns:           │  │  - Clamp to max 2 sentences           │   │   │
│  │  │  classification +   │  │  - Inject problem context             │   │   │
│  │  │  confidence         │  └──────────────────┬───────────────────┘   │   │
│  │  └──────────┬──────────┘                     │                        │   │
│  │             │                                 │                        │   │
│  │  ┌──────────▼─────────────────────────────────▼───────────────────┐  │   │
│  │  │              Response Generator (LLM call #2 or combined)       │  │   │
│  │  │  - Sends structured prompt to Claude claude-sonnet-4-6                  │  │   │
│  │  │  - Streams response tokens back                                  │  │   │
│  │  └──────────────────────────────────┬──────────────────────────────┘  │   │
│  └───────────────────────────────────────┬──────────────────────────────┘   │
│                               ┌───────────┘                                  │
│  ┌────────────────────────────▼───────────────────────────────────────────┐ │
│  │                       Problem Bank                                      │ │
│  │  - Static JSON file (MVP): 15 math problems, 3 difficulty levels       │ │
│  │  - Queried by orchestrator to fetch current problem + worked solution  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
└──────────────────────────────┬──────────────────────────────────────────────┘
                                │ Tutor text response
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                                    │
│                                                                               │
│  ┌──────────────────────┐    ┌──────────────────────┐                       │
│  │   AssemblyAI         │    │    ElevenLabs TTS     │                       │
│  │   Universal-3.5 Pro   │    │    - POST /v1/text-   │                       │
│  │   Streaming (v3 WS)   │    │      to-speech/stream │                       │
│  │   wss://streaming.    │    │    - Returns PCM/MP3   │                       │
│  │   assemblyai.com/     │    │      audio stream     │                       │
│  │   v3/ws               │    │                        │                       │
│  │   (Authorization      │    │                        │                       │
│  │   header; server-side │    │                        │                       │
│  │   only — never in     │    │                        │                       │
│  │   browser JS)          │    │                        │                       │
│  └──────────────────────┘    └──────────────────────┘                       │
│                                                                               │
│  ┌──────────────────────┐                                                    │
│  │   Anthropic API      │                                                    │
│  │   Claude claude-sonnet-4-6          │                                                    │
│  │   (reasoning +       │                                                    │
│  │    response gen)     │                                                    │
│  └──────────────────────┘                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 2b. Data Flow for a Single Turn

**Latency budget target: <2,000 ms end-to-end from end of speech to first audio byte.**

| Step | Description | Latency Target | Notes |
|---|---|---|---|
| 1 | User speaks — browser captures PCM audio chunks via WebAudio API | 0 ms (continuous) | 16-bit, 16kHz mono; 100 ms chunk size |
| 2 | Chunks forwarded over WebSocket to FastAPI server | +10–20 ms | Binary WS frames; minimal framing overhead |
| 3 | Server proxies raw audio (binary frames, 16-bit PCM) to AssemblyAI's v3 streaming WebSocket (`wss://streaming.assemblyai.com/v3/ws`, `speech_model=universal-3-5-pro`) | +10–20 ms | Keep the AssemblyAI WS connection persistent per session — billing is on WS-open duration, so reconnect-per-turn is both slower and more expensive |
| 4 | AssemblyAI returns partial `Turn` messages (`end_of_turn: false`) — first one at ~750 ms, then every ~3 s during a long turn (`continuous_partials`) | +200–750 ms from speech start | Server forwards `transcript` to client; UI shows live text |
| 5 | User stops speaking — AssemblyAI's punctuation-based turn detector fires after `min_turn_silence` (100 ms default) finds terminal punctuation, or forces the turn after `max_turn_silence` (1000 ms default); emits final `Turn` (`end_of_turn: true`, `turn_is_formatted: true`, `end_of_turn_confidence`) | +100–1000 ms from speech end | Turn Manager consumes this event; tune `min_turn_silence`/`max_turn_silence` for thinking pauses (see [§2d](#2d-turn-taking-and-barge-in-design)) |
| 6 | Turn Manager validates transcript; updates LearnerState attempt_count | +5 ms | In-memory operation |
| 7 | Tutor Orchestrator assembles structured prompt (problem context + learner state + transcript + classification instructions) | +10 ms | Template fill; no I/O |
| 8 | Single LLM call to Claude claude-sonnet-4-6 (combined reasoning classification + response generation in one prompt) | +400–700 ms | Use streaming; first token visible at ~400 ms |
| 9 | Response Policy enforces constraints: max 2 sentences, Socratic tone, strategy tag parsed from LLM JSON preamble | +5 ms | Parse JSON prefix, extract `strategy` + `response` |
| 10 | Tutor response text sent to ElevenLabs streaming TTS | +100–200 ms | Begin streaming as soon as LLM outputs first sentence |
| 11 | First audio byte received from ElevenLabs | +300–500 ms from TTS request | Pipeline with step 10 |
| 12 | Audio played back to learner via browser AudioContext | +20–50 ms buffering | Can begin before full response is received |
| **Total (p50)** | | **~1,100–1,600 ms** | Within 2 s budget |
| **Total (p95)** | | **~1,700–2,200 ms** | Occasionally over on slow connections |

**Streaming optimization:** Steps 8 and 10 are pipelined — as soon as the LLM outputs the first complete sentence (detected by period/newline), it is dispatched to TTS without waiting for the full response. This saves 200–400 ms on typical 2-sentence responses.

**Barge-in path:** If the client detects new voice activity while TTS is playing, it sends a `{type: "barge_in"}` control message over the WebSocket. The server cancels the ElevenLabs stream, discards buffered audio, and the Turn Manager resets to accept the new utterance. No additional latency beyond the normal path.

---

### 2c. Tutor Orchestrator Design

#### Pedagogical Loop

```
┌─────────────────────────────────────────────────────────┐
│                   Tutor Orchestrator Loop                │
│                                                          │
│  1. PROBLEM SELECTION                                    │
│     - On session start: pick problem at learner's        │
│       current difficulty level from problem bank        │
│     - On mastery: increment difficulty, new problem      │
│     - On 3 failed attempts: decrement difficulty         │
│                                                          │
│  2. LEARNER EXPLANATION CAPTURE                          │
│     - Receive validated utterance from Turn Manager      │
│     - Append to session_history as {role: "learner",     │
│       text: utterance, timestamp: now}                  │
│                                                          │
│  3. REASONING CLASSIFICATION                             │
│     - LLM classifies utterance against problem context   │
│     - Classification types:                              │
│       · CORRECT           — full correct reasoning       │
│       · PARTIALLY_CORRECT — right direction, gap exists  │
│       · MISCONCEPTION     — identified wrong model       │
│       · OFF_TOPIC         — unrelated to problem         │
│       · STUCK             — "I don't know" / silence     │
│       · CHALLENGE_READY   — correct + seeking more       │
│                                                          │
│  4. STRATEGY SELECTION (Response Policy)                 │
│     CORRECT        → ACKNOWLEDGE + CHALLENGE (if 1st)   │
│                       or NEXT_PROBLEM (if already pushed)│
│     PARTIALLY_CORRECT → PROBE (ask about the gap)       │
│     MISCONCEPTION  → COUNTEREXAMPLE or CORRECTION       │
│                       (prefer counterexample first)      │
│     OFF_TOPIC      → REDIRECT                            │
│     STUCK          → HINT (if attempt 1–2)              │
│                       SIMPLER_SUBPROBLEM (if attempt 3+) │
│     CHALLENGE_READY → CHALLENGE (harder variant)        │
│                                                          │
│  5. RESPONSE GENERATION CONSTRAINTS                      │
│     - Max 2 sentences                                    │
│     - Never give the answer directly                     │
│     - End with a question (Socratic constraint)          │
│     - Plain language (Grade 6 reading level)             │
│     - Acknowledge effort before redirecting              │
└─────────────────────────────────────────────────────────┘
```

#### LLM Prompt Structure

The orchestrator makes a **single combined call** per turn (classification + response generation together) to minimize latency. The prompt is structured as follows:

```
SYSTEM PROMPT (sent once at session init, cached):
────────────────────────────────────────────────────────────────
You are Priya, a warm and patient AI math tutor for Grade 8–10
students. Your teaching philosophy: never give answers directly.
Always guide students to discover the solution themselves through
questions. Use simple language (Grade 6 reading level). Speak in
English unless the student speaks in another language, then match
their language.

Response format (always respond with valid JSON):
{
  "classification": "<CORRECT|PARTIALLY_CORRECT|MISCONCEPTION|OFF_TOPIC|STUCK|CHALLENGE_READY>",
  "reasoning": "<1 sentence: why you classified this way>",
  "strategy": "<ACKNOWLEDGE|PROBE|HINT|COUNTEREXAMPLE|SIMPLER_SUBPROBLEM|CORRECTION|CHALLENGE|REDIRECT|NEXT_PROBLEM>",
  "response": "<Your spoken response to the student — max 2 sentences, end with a question>"
}

Constraints:
- response must be ≤ 40 words
- response must end with a question mark
- Never reveal the worked solution
- If student is correct, celebrate briefly then probe deeper OR advance
────────────────────────────────────────────────────────────────

USER TURN CONTEXT (assembled per turn):
────────────────────────────────────────────────────────────────
Current problem:
  ID: prob_007
  Text: "A train travels 240 km in 3 hours. What is its average speed?"
  Worked solution (DO NOT REVEAL): speed = distance / time = 240/3 = 80 km/h
  Difficulty: MEDIUM
  Concept: ratio and proportion

Learner state:
  Attempt number: 2
  Prior misconceptions this session: ["confused speed with distance"]
  Mastery level: 0.45 (developing)

Conversation history (last 3 turns):
  Tutor: "If you drove 100 km in 2 hours, how fast were you going?"
  Learner: "50 km/h"
  Tutor: "Exactly! So what operation did you use to get 50?"

Current learner utterance:
  "I divided 100 by 2... so for this one maybe divide 240 by 3?"

Classify and respond.
────────────────────────────────────────────────────────────────
```

**Expected LLM output:**
```json
{
  "classification": "PARTIALLY_CORRECT",
  "reasoning": "Student identified the correct operation (division) and numbers but has not stated the answer or the unit.",
  "strategy": "PROBE",
  "response": "Great thinking — you've got the right operation! What do you get when you actually divide 240 by 3, and what unit should your answer have?"
}
```

The `response` field is extracted and sent directly to TTS. The `classification` and `strategy` fields update LearnerState.

---

### 2d. Turn-Taking and Barge-In Design

#### End-of-Utterance Detection

> Corrected from v1.0: `is_final`/`TranscriptEvent`/`end_utterance_silence_threshold` are v2 API names and no longer exist. Universal-3.5 Pro Streaming (v3) uses **punctuation-based turn detection**, not the confidence-threshold model of the legacy Universal-Streaming models.

AssemblyAI's v3 `Turn` message provides the signals the Turn Manager needs:
1. `end_of_turn: true` / `turn_is_formatted: true` — the turn is complete and fully formatted (punctuation, casing, numbers). Treat a turn as done only when **both** flags are true.
2. `end_of_turn_confidence` (0.0–1.0) — model confidence that the turn genuinely ended, useful for the low-confidence gate below.
3. Two connection parameters control *when* that decision fires:
   - `min_turn_silence` (default `100` ms) — silence before the model runs a speculative check for terminal punctuation (`.` `?` `!`). If found, the turn ends immediately.
   - `max_turn_silence` (default `1000` ms) — hard ceiling; the turn is forced to end here regardless of punctuation.

For this product, raise `min_turn_silence` to **~400–500 ms** (not the old `end_utterance_silence_threshold=700` value, which doesn't map 1:1 onto the new model) — the default 100 ms is tuned for quick dictation and will split a thinking learner's sentence at every comma-less pause (see AssemblyAI's own example: `min_turn_silence=100` turns `"It's john.smith@gmail.com."` into three separate finals). Both parameters can be tuned mid-session via `UpdateConfiguration` without reconnecting.

The Turn Manager's confirmation gate becomes:
- `end_of_turn: true` **and** `turn_is_formatted: true` received → trigger turn processing.
- If `end_of_turn_confidence` is low despite the flags, fall through to the low-confidence handling below rather than trusting the boundary blindly.

#### Barge-In Handling

```
State machine for TTS playback:

  IDLE → [learner speaks] → CAPTURING
  CAPTURING → [end-of-utterance] → PROCESSING
  PROCESSING → [LLM response ready] → SPEAKING
  SPEAKING → [barge-in detected] → CAPTURING  ← immediate cancel
  SPEAKING → [TTS complete] → IDLE

Barge-in trigger:
  Client-side: WebAudio analyser detects RMS energy above threshold
  for >200 ms while in SPEAKING state.
  Client sends: {"type": "barge_in", "session_id": "..."}
  Server: cancels ElevenLabs HTTP stream, clears TTS buffer,
  transitions state machine to CAPTURING.
```

#### Silence Timeout

- If no speech detected for 15 seconds after the tutor's question: server sends a `{type: "silence_timeout"}` event.
- Turn Manager synthesizes a virtual "STUCK" utterance and triggers the HINT strategy.
- Prevents sessions hanging silently — common with shy or confused learners.

#### Low-Confidence Transcript Handling

- On each final `Turn`, compute the mean of `words[].confidence` (each word in the `words` array carries `confidence` and `word_is_final`). If that average, or `end_of_turn_confidence`, is `< 0.70`: do not process as a learner turn.
- Instead, tutor responds: "Sorry, I didn't catch that clearly — could you say that again?"
- If confidence < 0.70 for 3 consecutive utterances: log as `stt_low_confidence_streak` metric, suggest text fallback (Phase 2 feature).
- Confidence threshold is configurable per language (lower threshold for accented speech during calibration).
- Use `keyterms_prompt` (and optionally `prompt`) at connection time to bias recognition toward domain vocabulary — math terms and problem-specific names (e.g. `["ratio", "proportion", "speed", "BKT"]`) — which reduces low-confidence transcripts on exactly the words the tutor cares about most.

---

### 2e. MVP Tech Stack (Final Recommendation)

| Component | Technology | Justification |
|---|---|---|
| STT | AssemblyAI Universal-3.5 Pro Streaming (v3 WebSocket, `speech_model=universal-3-5-pro`) | Hackathon requirement; native Hindi↔English code-switching (no separate Hinglish handling needed); word-level `Turn` events enable partial UI |
| LLM | Claude claude-sonnet-4-6 (Anthropic API) | Best instruction-following for constrained Socratic prompts; structured JSON output; built-in safety |
| TTS | ElevenLabs streaming TTS | Most natural voice quality; streaming API minimizes latency; simple REST integration |
| Frontend | React + Vite |  |
| Backend | FastAPI + uvicorn (Python 3.11) | Async WebSocket; native AssemblyAI + Anthropic Python SDKs; async generators for streaming |
| State (MVP) | Python in-memory dict + SQLite | Zero ops; sufficient for single-session hackathon demo |
| Problem Bank | Static JSON file | 15 problems sufficient for MVP; trivial to expand |
| Deployment | Vercel (frontend) + Railway (backend) / Render (for both) | One-command GitHub deploy; free tiers sufficient for demo |
| Audio capture | WebAudio API (browser-native) | No library needed; PCM capture at 16kHz |
| Transport | WebSocket (binary for audio, JSON for control) | Bidirectional; low overhead; native browser support |

---

## 3. Phase 2 Architecture Changes

### 3.1 Persistent Learner Model Schema (PostgreSQL via Supabase)

```sql
-- Core learner profile
CREATE TABLE learners (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT now(),
    name TEXT NOT NULL,
    grade INTEGER CHECK (grade BETWEEN 6 AND 12),
    primary_language TEXT DEFAULT 'en',  -- BCP-47: 'hi', 'ta', 'te', 'en'
    school_id UUID REFERENCES schools(id),
    -- Aggregate mastery snapshot (denormalized for fast reads)
    overall_mastery FLOAT DEFAULT 0.0,
    last_session_at TIMESTAMPTZ
);

-- Skill-level mastery tracking (one row per learner per skill)
CREATE TABLE learner_skills (
    learner_id UUID REFERENCES learners(id),
    skill_code TEXT NOT NULL,  -- e.g., 'math.ratio.speed_distance_time'
    -- BKT parameters
    p_know FLOAT DEFAULT 0.3,   -- P(Learned) — Bayesian Knowledge Tracing
    p_transit FLOAT DEFAULT 0.1, -- P(Learn | not known)
    p_slip FLOAT DEFAULT 0.1,    -- P(Wrong | known)
    p_guess FLOAT DEFAULT 0.2,   -- P(Right | not known)
    attempt_count INTEGER DEFAULT 0,
    correct_count INTEGER DEFAULT 0,
    last_practiced_at TIMESTAMPTZ,
    PRIMARY KEY (learner_id, skill_code)
);

-- Session records
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    learner_id UUID REFERENCES learners(id),
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at TIMESTAMPTZ,
    subject TEXT,
    language TEXT,
    problems_attempted INTEGER DEFAULT 0,
    problems_mastered INTEGER DEFAULT 0,
    total_turns INTEGER DEFAULT 0,
    summary JSONB  -- SessionSummary struct
);

-- Turn-level log (used for offline analysis, not hot path)
CREATE TABLE turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    turn_index INTEGER,
    timestamp TIMESTAMPTZ DEFAULT now(),
    utterance TEXT,
    stt_confidence FLOAT,
    classification TEXT,
    strategy TEXT,
    tutor_response TEXT,
    latency_ms INTEGER
);

-- Misconception tracking
CREATE TABLE misconceptions (
    learner_id UUID REFERENCES learners(id),
    skill_code TEXT,
    misconception_type TEXT,  -- e.g., 'confuses_speed_with_distance'
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    occurrence_count INTEGER DEFAULT 1,
    resolved BOOLEAN DEFAULT false,
    PRIMARY KEY (learner_id, skill_code, misconception_type)
);
```

**Hot path (Redis/Upstash):** Active session `LearnerState` lives in Redis with a 2-hour TTL. On session end, flush to PostgreSQL. Redis key: `session:{session_id}:state` (JSON, ~2 KB).

---

### 3.2 Multilingual / Vernacular STT Strategy

**Phase 2 language routing architecture:**

```
Incoming session:
  → Learner selects language at session start (or auto-detect on first utterance)
  → Language code stored in LearnerState.primary_language

STT routing (AssemblyAI Universal-3.5 Pro Streaming supports 18 languages
with native code-switching: en, es, de, fr, pt, it, tr, nl, sv, no, da, fi,
hi, vi, ar, he, ja, zh — Tamil and Telugu are NOT in that list, at any
accuracy level, so they cannot be routed to AssemblyAI even as a stretch):
  - 'en', 'en-IN' (Indian English)  → AssemblyAI (universal-3-5-pro)
  - 'hi' (Hindi), incl. Hinglish    → AssemblyAI (universal-3-5-pro)
                                       — no separate fallback needed; the
                                       model code-switches en/hi natively
                                       in a single connection
  - 'ta' (Tamil), 'te' (Telugu)     → Google STT v2 (only viable option —
                                       AssemblyAI has zero support, not
                                       just weaker accuracy)
  - 'bn' (Bengali), 'mr' (Marathi)  → Google STT v2
  - Other / unknown                  → Google STT v2 multilingual model
                                       with language detection

Code-switching handling (Hinglish):
  - AssemblyAI: pass language_codes=["en","hi"] to bias the model (native
    code-switching works without this, but biasing improves accuracy when
    the mix is known in advance); set language_detection=true to get
    language_code/language_confidence back on each Turn
  - Deepgram (Phase 2 alt): supports dual-language mode (en + hi simultaneously)
  - Google STT (Tamil/Telugu path): use 'hi-IN' as primary with
    alternative_language_codes=['en-IN'] where code-switching is needed
  - LLM prompt instructs Claude to respond in the detected mix
```

**TTS language routing:**
- Hindi: Google Neural2 `hi-IN-Neural2-A` (female, warm)
- Tamil: Google Neural2 `ta-IN-Neural2-A`
- Telugu: Google Neural2 `te-IN-Neural2-A`
- English: ElevenLabs (retain for English sessions; better naturalness)

---

### 3.3 Hesitation and Uncertainty Detection

Hesitation signals are extracted from AssemblyAI's word-level data in each `Turn` message — every entry in the `words[]` array carries `start`/`end` (ms), `text`, `confidence`, and `word_is_final`:

| Signal | Detection Method | Threshold | Interpretation |
|---|---|---|---|
| Long pauses mid-utterance | Gap between consecutive `words[].start`/`words[].end` timestamps > 1.5 s | >1.5 s | Learner searching for words; not ready — extend silence timeout |
| Filler words | Transcript contains "um", "uh", "hmm", "I think maybe" | Presence | Uncertainty; consider HINT even if answer is correct |
| False starts | A partial `Turn`'s transcript (`end_of_turn: false`) later contradicted by the final `Turn` (`end_of_turn: true`) for the same `turn_order` | Detected | Learner reconsidering; log but don't penalize |
| Speech rate drop | Words-per-minute in current utterance < 50% of session baseline | <50% WPM | Cognitive load; simplify next prompt |
| Low confidence | Mean `words[].confidence` for the turn < 0.75 | <0.75 | May indicate mumbling under uncertainty |

These signals are combined into a `hesitation_score` (0.0–1.0) attached to each turn. The Response Policy uses `hesitation_score > 0.6` to soften the strategy (e.g., prefer HINT over PROBE even on PARTIALLY_CORRECT classification).

---

### 3.4 Skill Mastery Tracking Algorithm

Phase 2 uses **Bayesian Knowledge Tracing (BKT)** — simple, interpretable, and well-validated in ITS research.

**BKT parameters (per skill):**
- `P(L₀)` = prior probability of knowing skill = 0.3 (default)
- `P(T)` = probability of learning per attempt = 0.1
- `P(S)` = probability of slip (know but answer wrong) = 0.1
- `P(G)` = probability of guess (don't know but answer correct) = 0.2

**Update equation after each attempt:**

```python
def bkt_update(p_know, p_transit, p_slip, p_guess, is_correct):
    """
    Update P(Learned) after observing a correct or incorrect response.
    """
    if is_correct:
        p_correct_given_know = 1 - p_slip
        p_correct_given_not = p_guess
    else:
        p_correct_given_know = p_slip
        p_correct_given_not = 1 - p_guess

    # P(know | observation) via Bayes
    numerator = p_correct_given_know * p_know
    denominator = numerator + p_correct_given_not * (1 - p_know)
    p_know_given_obs = numerator / denominator

    # Apply learning transition
    p_know_new = p_know_given_obs + (1 - p_know_given_obs) * p_transit
    return p_know_new

# Mastery threshold: P(know) >= 0.95 → skill mastered
# Advance to next problem when mastered
# Retreat to simpler subproblem when P(know) < 0.2 after 3 attempts
```

**Skill taxonomy (MVP subset, Math):**
```
math
├── arithmetic
│   ├── math.arith.fractions
│   └── math.arith.percentages
├── algebra
│   ├── math.alg.linear_equations
│   └── math.alg.word_problems
└── ratio_proportion
    ├── math.ratio.basic
    └── math.ratio.speed_distance_time
```

---

### 3.5 Teacher / Parent Dashboard API Design

```
REST API (FastAPI, JWT-authenticated):

GET  /api/v1/learners/{learner_id}/summary
     Response: LearnerSummary { name, grade, sessions_count,
               skills: [{code, p_know, trend}], recent_misconceptions }

GET  /api/v1/learners/{learner_id}/sessions?limit=10&offset=0
     Response: PaginatedSessions { sessions: [SessionRecord], total }

GET  /api/v1/learners/{learner_id}/sessions/{session_id}
     Response: SessionDetail { summary, turns: [TurnRecord], metrics }

GET  /api/v1/classrooms/{classroom_id}/learners
     Response: ClassroomRoster with aggregate mastery heatmap data

GET  /api/v1/classrooms/{classroom_id}/skills/gap-analysis
     Response: [{skill_code, avg_p_know, struggling_learners: [id]}]

POST /api/v1/learners/{learner_id}/assign-problem-set
     Body: { problem_ids: [...], due_date: "..." }
     Response: AssignmentRecord

WebSocket /ws/classroom/{classroom_id}/live
     Push: real-time session-start/end events for active sessions
     Use: teacher can see which students are actively practicing
```

Authentication: Supabase Auth (email/password for teachers; magic link for parents). Row-Level Security ensures teachers only see their classroom's data.

---

## 4. Phase 3 Architecture Changes

### 4.1 Camera / Image Input Pipeline

```
┌──────────────────────────────────────────────────────────────────┐
│                    Multimodal Input Pipeline                      │
│                                                                   │
│  Camera Frame (JPEG/WebP)                                        │
│       │                                                           │
│       ▼                                                           │
│  ┌────────────────────┐                                          │
│  │  Image Preprocessor│  ← Run in-browser (TensorFlow.js)        │
│  │  - Motion detect   │    or on server                          │
│  │  - Quality check   │                                          │
│  │  - Crop to content │                                          │
│  └────────┬───────────┘                                          │
│           │                                                       │
│           ▼                                                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              OCR + Visual Understanding                     │  │
│  │                                                            │  │
│  │  Handwriting OCR:                                          │  │
│  │  - Google Vision API (best handwriting accuracy)           │  │
│  │  - OR Claude claude-sonnet-4-6 Vision (if already using Claude)    │  │
│  │  - Output: extracted mathematical expression text          │  │
│  │                                                            │  │
│  │  Diagram Understanding:                                    │  │
│  │  - Claude claude-sonnet-4-6 Vision: "What math concept does this   │  │
│  │    diagram show? Identify any errors."                     │  │
│  │  - Output: structured description + error flags            │  │
│  └────────────────────────────────────────────────────────────┘  │
│           │                                                       │
│           ▼                                                       │
│  Merged input to Tutor Orchestrator:                             │
│  { utterance: "...", image_context: { ocr_text: "...",          │
│    diagram_description: "...", detected_errors: [...] } }       │
└──────────────────────────────────────────────────────────────────┘
```

**Trigger logic:** Camera input is optional and event-driven. The learner can say "look at this" or press a capture button. The system does not continuously process video — it captures a single frame on trigger to keep compute and cost bounded.

**Latency impact:** Image understanding adds ~400–800 ms (Google Vision) or ~600–1,200 ms (Claude Vision) to the turn latency. Show a "thinking..." indicator during this phase.

---

### 4.2 Visual Whiteboard Alongside Voice

The whiteboard is a collaborative canvas rendered in the browser:

- **Technology:** Excalidraw embedded component (MIT license, React-native, excellent math drawing tools)
- **Sync:** Yjs CRDT (conflict-free replicated data type) over WebSocket for real-time sync between learner and tutor "agent cursor"
- **Tutor agent actions on whiteboard:**
  - Highlight a specific part of the learner's work (bounding box overlay)
  - Draw a counter-example diagram
  - Write a scaffolding equation step
- **Implementation:** The tutor orchestrator generates `whiteboard_actions` alongside the voice response:
  ```json
  {
    "response": "You've got the distance right — now what about the time?",
    "whiteboard_actions": [
      {"type": "highlight", "region": "bottom_left", "label": "time = ?"},
      {"type": "draw_arrow", "from": "240km", "to": "3h"}
    ]
  }
  ```

---

### 4.3 Curriculum Planning Agent Design

The curriculum planner is a separate agent that runs **asynchronously** (not on the critical voice path):

```
Curriculum Planning Agent (runs nightly or on session end):

Inputs:
  - LearnerState history (last 30 days)
  - Skill mastery profile (BKT p_know for all skills)
  - Curriculum graph (prerequisite relationships between skills)
  - Target exam / syllabus (e.g., CBSE Grade 9 Math)

Process:
  1. Identify skills with p_know < 0.5 that are prerequisites for
     target exam topics → "foundation gaps"
  2. Rank by: (prerequisite_depth × (1 - p_know)) for priority
  3. Generate a 2-week study plan: ordered sequence of skills
     with estimated session count per skill
  4. Detect readiness for exam topics: if all prerequisites
     p_know >= 0.8 → mark topic as "ready to practice"

Output (stored in DB, surfaced to teacher dashboard):
  CurriculumPlan {
    learner_id, generated_at, target_exam, target_date,
    weeks: [{ week_num, skills: [{ code, sessions_recommended }] }],
    readiness_score: 0.0–1.0,
    at_risk_topics: [{ topic, blocking_skills: [...] }]
  }

Implementation: LangGraph agent or simple Python scheduler
  (LangGraph for Phase 3; simple cron for Phase 2 preview)
```

---

## 5. Production Readiness Checklist

### 5.1 Latency Optimization

| Technique | Implementation | Expected Gain |
|---|---|---|
| LLM response streaming | Use Anthropic streaming API; begin TTS as first sentence completes | -300 to -500 ms |
| TTS audio caching | Cache ElevenLabs output for repeated phrases (15–20 common tutor phrases) using Redis; cache key = hash(text + voice_id) | -300 ms for cache hits; ~30% of tutor turns hit cache |
| AssemblyAI WS keep-alive | Maintain persistent WS connection per session; do not reconnect per turn | -200 ms reconnect overhead |
| Prompt caching (Anthropic) | Mark system prompt as cacheable using `cache_control: {"type": "ephemeral"}` header; system prompt is identical across turns | -50 to -100 ms on cached turns; ~90% cache hit after first turn |
| Edge deployment for static assets | Vercel CDN for frontend | -50 to -200 ms global |
| Connection pooling | SQLAlchemy async pool for PostgreSQL (Phase 2+) | -10 to -30 ms |

### 5.2 Scalability

- **Stateless backend services:** All session state in Redis; any FastAPI pod can handle any session. Enable horizontal scaling via Railway/ECS service auto-scaling.
- **WebSocket session affinity:** Use sticky sessions (Railway supports this) OR route all WS frames through a Redis pub/sub channel so any pod can pick up the session. Prefer sticky sessions for simplicity until >500 concurrent users.
- **Audio processing:** Audio byte forwarding (microphone → AssemblyAI) is pure proxying; near-zero CPU. A single uvicorn worker handles ~200 concurrent WebSocket sessions.
- **LLM concurrency:** Anthropic API rate limits: 4,000 RPM on Tier 3. At 1 LLM call per 10-second turn average, one learner = ~6 calls/min. Supports ~650 concurrent learners before rate limiting. Request Tier 4 at scale.
- **CDN for audio:** TTS audio for cached phrases served from CDN (store in S3-compatible bucket, CloudFront/Cloudflare URL).

### 5.3 Reliability

| Failure Mode | Fallback | Implementation |
|---|---|---|
| AssemblyAI STT outage | Deepgram Nova-2 as hot standby; route switch in <1 s via feature flag | Environment variable `STT_PROVIDER`; health check every 30 s |
| Anthropic API outage | GPT-4o as fallback LLM; same structured prompt format | Try-except with exponential backoff (3 retries, 500 ms / 1 s / 2 s); then switch model |
| ElevenLabs TTS outage | Google Neural TTS fallback; slightly less natural but functional | Same pattern as LLM fallback |
| WebSocket disconnect | Client auto-reconnect with exponential backoff; session state preserved in Redis for 2 hours | WS reconnect logic in frontend; session_id in localStorage |
| Offline/poor connectivity | Graceful degradation: show "voice unavailable" + text input fallback | Detect WS failure; render text input; submit via REST endpoint |

### 5.4 Security

| Concern | Implementation |
|---|---|
| API key management | All external API keys in environment variables; never in client bundle. Railway/Vercel secrets management. Key rotation documented in runbook. |
| Content safety (minors) | Anthropic's built-in safety filters + custom system prompt clause: "Refuse any request unrelated to the current academic subject. Do not engage with personal, social, or adult topics." Log refused requests. |
| Student data privacy | No PII in LLM prompts (use learner_id, never name/school). Implement data retention policy: turn logs deleted after 90 days; aggregate summaries kept. |
| COPPA/DPDP (India) considerations | Collect only necessary data (grade, language preference). Parental consent flow for learners under 13. No advertising IDs or third-party tracking. Supabase RLS ensures data isolation. |
| Audio data | Raw audio is NOT stored — only transcripts. AssemblyAI audio is streamed and discarded. Add `audio_retention: false` to AssemblyAI config. |
| Transport security | WSS (WebSocket Secure) + HTTPS everywhere. HSTS enabled. |
| Rate limiting | FastAPI middleware: 100 requests/minute per IP for REST; WS connections limited to 3 per learner_id. |

### 5.5 Observability

**Metrics to instrument (Prometheus + Grafana, or Datadog for Phase 3):**

| Metric | Description | Alert Threshold |
|---|---|---|
| `session_completion_rate` | % of sessions that end with a session summary (vs. drop) | Alert if <70% |
| `correction_cycle_rate` | Avg turns before a misconception is resolved | Alert if >8 turns |
| `stt_error_rate` | % of utterances with confidence <0.70 | Alert if >15% |
| `latency_p50_ms` / `latency_p95_ms` | End-to-end turn latency | p95 alert if >2,500 ms |
| `llm_fallback_rate` | % of turns using fallback LLM | Alert if >5% |
| `tts_cache_hit_rate` | % of TTS requests served from cache | Monitor for optimization |
| `barge_in_rate` | % of turns with barge-in | High rate = tutor talking too long |
| `silence_timeout_rate` | % of turns ending with silence timeout | High rate = learners stuck |

**Structured logging:** Every turn logged as JSON:
```json
{
  "event": "turn_complete",
  "session_id": "...",
  "turn_index": 3,
  "classification": "MISCONCEPTION",
  "strategy": "COUNTEREXAMPLE",
  "stt_end_of_turn_confidence": 0.89,
  "latency_ms": 1423,
  "stt_provider": "assemblyai",
  "llm_model": "claude-sonnet-4-6",
  "tts_cache_hit": false
}
```

### 5.6 Cost Optimization

**Per-session cost estimate (30-minute session, ~18 turns):**

| Component | Usage | Unit Cost | Cost per Session |
|---|---|---|---|
| AssemblyAI STT (Universal-3.5 Pro Streaming) | 30 min **session duration** (WS open time, not audio sent) | $0.45/hr | $0.225 |
| Claude claude-sonnet-4-6 LLM | 18 turns × ~800 tokens avg (in+out) | $3/$15 per 1M | ~$0.07 |
| ElevenLabs TTS | 18 turns × ~30 words × 5 chars = ~2,700 chars; minus cache hits | $0.30/1K chars | ~$0.005 (w/ caching) |
| **Total** | | | **~$0.30/session** |

> AssemblyAI streaming bills on **WebSocket session duration**, not audio volume — an idle connection accrues cost just like an active one, and a session left open auto-closes (and bills for) up to 3 hours if the server never sends `{"type": "Terminate"}`. Always terminate explicitly when a learner session ends; don't rely on the timeout.

**Cost levers:**
- STT is the dominant cost. Phase 2: Deepgram at $0.59/hr is *not* cheaper than AssemblyAI's $0.45/hr any more — re-evaluate that Phase 2 assumption; Deepgram's case now rests on latency/accent accuracy, not price.
- LLM token budgets: enforce max 800 tokens output per turn in API call (`max_tokens=200`). System prompt caching (Anthropic) cuts input cost ~70% on cached tokens.
- TTS caching: 20 pre-rendered audio files for common phrases (hints, acknowledgments) stored in CDN. Eliminates TTS cost for ~30% of turns.
- Problem bank avoids LLM calls for problem selection — problems are pre-authored.

---

## 6. Architecture Decision Records (ADRs)

### ADR-001: AssemblyAI for STT (MVP Constraint)

**Status:** Accepted (constrained by hackathon requirement)  
**Date:** 2026-09-06

**Context:**  
The product is being built for the AssemblyAI Voice Agent Hackathon 2026. AssemblyAI must be used as the STT provider for MVP.

**Decision:**  
Use AssemblyAI's **Universal-3.5 Pro Streaming** model over the **v3 WebSocket API** (`wss://streaming.assemblyai.com/v3/ws?speech_model=universal-3-5-pro`, `Authorization` header, server-side only) for all STT in MVP. Tune turn detection via `min_turn_silence` (raise from the 100 ms default to ~400–500 ms) and `max_turn_silence` (1000 ms default) to suit learner thinking pauses — this replaces the v2-era `end_utterance_silence_threshold` parameter, which does not exist in v3.

> **Updated from v1.0 of this doc**, which specified the retired v2 endpoint (`api.assemblyai.com/v2/realtime`), the retired `TranscriptEvent`/`is_final` message schema, and the deprecated `end_utterance_silence_threshold` parameter. v3 uses typed `Begin`/`Turn`/`Termination` messages and punctuation-based turn detection instead of a single silence threshold. See [§2d](#2d-turn-taking-and-barge-in-design) for the corrected design.

**Consequences — Positive:**
- AssemblyAI has strong Indian English accuracy. Real-time word-level events enable partial transcript UI that gives learners immediate feedback. Well-documented Python SDK. Built-in punctuation formatting.
- **Native Hindi↔English code-switching in one model** — Universal-3.5 Pro Streaming code-switches across 18 languages (including Hindi) in a single connection, which fully resolves the Hinglish gap this ADR originally flagged as unsolved. No dual-model or language-tagging workaround is needed for English/Hindi mixing.
- Cheaper than assumed at v1.0: $0.45/hr session-duration billing, not $0.65/hr.

**Consequences — Negative:**
- **Tamil and Telugu are not supported at any accuracy level** — they are absent from Universal-3.5 Pro Streaming's 18-language list entirely (en, es, de, fr, pt, it, tr, nl, sv, no, da, fi, hi, vi, ar, he, ja, zh). This is a harder constraint than "inferior accuracy" as originally written — there is no AssemblyAI code path for these two languages, so Phase 2's Google STT routing for Tamil/Telugu ([§3.2](#32-multilingual--vernacular-stt-strategy)) is mandatory, not optional.
- Streaming is billed on WebSocket session duration, including idle time — sessions must be explicitly terminated (`{"type": "Terminate"}`) or they auto-close (and bill) after 3 hours.

**Migration Path (Phase 2):**
- Abstract STT behind a `STTProvider` interface from day one:
  ```python
  class STTProvider(Protocol):
      async def stream(self, audio_chunk: bytes) -> AsyncIterator[TurnEvent]: ...
  ```
- Implement `AssemblyAIProvider` and `DeepgramProvider` behind this interface. Route by language code via factory pattern — English and Hindi (including Hinglish) stay on AssemblyAI; Tamil, Telugu, Bengali, and Marathi route to Google STT v2 unconditionally. Switching providers requires zero change to Turn Manager or Orchestrator.

**Review trigger:** Reassess if AssemblyAI Hindi accuracy in production is below 85% word accuracy, or if Phase 2 vernacular requirements (Tamil/Telugu) are unmet — expected, since AssemblyAI cannot serve them at all.

---

### ADR-002: LLM Selection for Tutor Reasoning

**Status:** Accepted  
**Date:** 2026-09-06

**Context:**  
The tutor orchestrator requires a model that can: (a) classify learner reasoning reliably from a structured prompt, (b) generate Socratic responses constrained to 2 sentences and a question, (c) output valid JSON reliably, (d) handle multilingual input, (e) maintain content safety for minors.

**Decision:**  
Use **Claude claude-sonnet-4-6** (claude-sonnet-4-6) as primary LLM. GPT-4o as hot fallback (identical structured prompt; both support JSON mode).

**Rationale:**
- Claude excels at following constrained output formats (max 2 sentences, must-end-with-question) vs. GPT-4o which occasionally violates soft constraints.
- Anthropic's Constitutional AI safety filters are well-suited for minor-facing applications without additional moderation layer.
- Extended thinking mode (claude-sonnet-4-6) is available for complex multi-step reasoning in Phase 2 without changing providers.
- Anthropic prompt caching reduces cost on the repeated system prompt (estimated 90% cache hit rate after warm-up).

**Consequences — Negative:**
- Anthropic rate limits at lower tiers require early tier upgrade planning.
- Slightly higher per-token cost vs. Gemini 1.5 Pro for the same output quality.

**Rejected alternatives:**
- Gemini 1.5 Pro: higher latency (p50 ~800 ms vs ~600 ms); JSON output less reliable in early testing.
- Llama 3.3 70B self-hosted: excellent cost at scale but requires MLOps infrastructure, adds 4–6 weeks of setup, and quality on Socratic pedagogy prompts is inferior.

---

### ADR-003: TTS Provider Selection

**Status:** Accepted  
**Date:** 2026-09-06

**Context:**  
TTS quality directly affects learner engagement. A robotic or harsh voice causes drop-off in younger users, especially in a tutoring context where the voice must convey warmth and patience. Indic language support is needed for Phase 2.

**Decision:**  
**ElevenLabs streaming TTS** for English MVP. **Google Neural2 TTS** for Indic languages in Phase 2.

**Rationale:**
- ElevenLabs produces the most natural, warm voice quality available commercially. The streaming API enables sentence-by-sentence audio delivery, supporting the pipeline optimization that saves 300–500 ms.
- Google Neural2 TTS has the most comprehensive Indic voice catalog (Hindi, Tamil, Telugu, Bengali, Marathi) with good naturalness. ElevenLabs Hindi voice is available but accent quality is inferior to Google for regional learners.

**Consequences — Negative:**
- Two TTS providers adds integration complexity. Mitigated by `TTSProvider` interface abstraction.
- ElevenLabs character-based pricing can spike if response verbosity is not controlled. Mitigated by enforcing max 40-word constraint in LLM prompt.

---

### ADR-004: State Management Approach — Explicit State vs. Chat History

**Status:** Accepted  
**Date:** 2026-09-06

**Context:**  
Two approaches for tracking learner progress: (A) maintain the full conversation history and pass it to the LLM for context, or (B) maintain an explicit `LearnerState` struct updated after each turn and inject only the relevant summary into each LLM prompt.

**Decision:**  
**Explicit state (B)**, with a rolling window of the last 3 turns from conversation history included in the prompt for conversational coherence.

**Rationale:**
- A 30-minute session with 18 turns would accumulate ~5,000 tokens of history. Passing full history on every turn increases cost linearly and latency noticeably.
- Explicit state (LearnerState: current_problem, mastery_by_skill, misconceptions, attempt_count) captures the pedagogically relevant information in ~300 tokens regardless of session length.
- The last 3 turns are sufficient for conversational flow — the tutor does not need to recall turn 1 to respond to turn 18.
- Explicit state enables programmatic BKT updates (ADR-002) that would be unreliable if left to LLM memory.

**Consequences — Negative:**
- State schema must be maintained carefully; any bug in state updates degrades pedagogy.
- LLM cannot "remember" a touching moment from earlier in the session for motivational callbacks. Acceptable trade-off for MVP.

---

### ADR-005: Monolith vs. Microservices for MVP

**Status:** Accepted  
**Date:** 2026-09-06

**Context:**  
Architecture style decision for the backend: a single FastAPI monolith vs. separate services for STT proxy, orchestration, state, and TTS.

**Decision:**  
**Single FastAPI monolith** for MVP and Phase 2. Refactor to services at Phase 3 if load warrants.

**Rationale:**
- The MVP must be built in 1–2 days. Microservices add service discovery, inter-service authentication, deployment complexity, and distributed tracing overhead that is not justified at this scale.
- The orchestration flow is inherently sequential and low-latency-sensitive (STT → state → LLM → TTS). Inter-service HTTP calls would add 10–30 ms per hop × 4 hops = 40–120 ms unnecessary overhead.
- FastAPI with async handlers scales to hundreds of concurrent WebSocket sessions on a single process. Railway/Render auto-scaling adds more pods when needed.
- Internal module boundaries (STT module, orchestrator module, state module, TTS module) are enforced by Python package structure — this provides a clean migration path to microservices at Phase 3 without re-architecting logic.

**Review trigger:** When concurrent sessions consistently exceed 500 or when team size exceeds 6 engineers (Conway's Law threshold).

---

## 7. Implementation Roadmap with Milestones

### Hackathon MVP — Target: 1–2 Days

Tasks are ordered by dependency. Parallel work is marked **[P]**.

| # | Task | Est. Hours | Notes |
|---|---|---|---|
| 1 | **AssemblyAI v3 WebSocket integration** — server-side proxy to `wss://streaming.assemblyai.com/v3/ws` (`speech_model=universal-3-5-pro`), forward audio from browser WS to AssemblyAI WS, receive `Begin`/`Turn`/`Termination` events, forward partials to client | 3 h | Core plumbing; blocks everything |
| 2 | **Browser audio capture** — WebAudio API, PCM at 16kHz, binary WS to server, waveform visualizer component | 2 h | **[P with 1]** if two people |
| 3 | **Turn detection + barge-in handler** — consume `end_of_turn: true` / `turn_is_formatted: true` events, tune `min_turn_silence`/`max_turn_silence`, silence timeout (15 s), barge-in control message handler | 2 h | Depends on 1 |
| 4 | **Problem bank** — author 15 math problems (5 per difficulty level: easy/medium/hard) in JSON, problem selection logic | 1.5 h | **[P]** — can be done while 1–3 runs |
| 5 | **Tutor orchestrator + reasoning classifier** — system prompt, user turn template, single LLM call (classification + response), JSON parsing | 3 h | Depends on 3 |
| 6 | **Response policy** — strategy→response mapping, constraint enforcement, misconception logging to LearnerState | 1.5 h | Depends on 5 |
| 7 | **ElevenLabs TTS integration** — streaming POST, pipe audio bytes back to client WS, client AudioContext playback | 2 h | Depends on 5 |
| 8 | **Session state** — in-memory LearnerState dict, SQLite persistence on session end | 1 h | **[P with 5]** |
| 9 | **Session summary generation** — end-of-session LLM call with session history, return SessionSummary JSON | 1 h | Depends on 8 |
| 10 | **Basic React UI** — voice button, waveform, partial transcript display, tutor response text, session summary card | 3 h | **[P with 1–3]** once WS contract defined |
| 11 | **Integration testing + demo polish** — happy path end-to-end, fix latency, pick demo problem set | 2 h | After all above |
| **Total** | | **~22 h** | Achievable in 2 days with 2 people |

**Demo script:** Learner attempts "train speed" problem (prob_007). Makes a misconception (confuses speed with distance). Tutor identifies it, offers counterexample (bicycle scenario). Learner self-corrects. Session summary shown.

---

### Phase 2 — Adaptive Tutor (Months 1–3 Post-Hackathon)

| Month | Milestone | Key Deliverables |
|---|---|---|
| Month 1 | **Persistent Learner Model** | PostgreSQL schema deployed on Supabase; BKT skill tracking; session history API; learner profile page |
| Month 1 | **Multi-Subject Support** | Science problem bank (physics: motion, light); skill taxonomy extended; subject selection in UI |
| Month 2 | **Hindi Language Support** | Deepgram Nova-2 Hindi STT integration; Google Neural2 Hindi TTS; Hindi tutor prompt variant; 15 Hindi-language problems |
| Month 2 | **Hesitation Detection** | Word-timing analysis on AssemblyAI events; hesitation_score implementation; softened strategy policy |
| Month 3 | **Teacher Dashboard v1** | REST API for learner summaries; classroom roster; skill gap heatmap; Next.js dashboard pages (read-only) |
| Month 3 | **Production Hardening** | LLM fallback (GPT-4o); STT fallback (Deepgram); structured logging; Datadog or similar; load test to 200 concurrent |

---

### Phase 3 — Multimodal Agent (Months 4–9)

| Month | Milestone | Key Deliverables |
|---|---|---|
| Month 4 | **Camera Input MVP** | One-tap photo capture; Google Vision OCR for handwritten equations; OCR text injected into tutor prompt |
| Month 5 | **Visual Whiteboard** | Excalidraw integration; Yjs sync; tutor agent highlight + annotation actions; voice + whiteboard synchronized |
| Month 6 | **Tamil and Telugu Support** | Google STT/TTS for 2 more languages; translated problem bank (100 problems/language); locale routing |
| Month 7 | **Curriculum Planning Agent** | Skill prerequisite graph; nightly BKT analysis; generated 2-week study plan; surfaced on teacher dashboard |
| Month 8 | **Parent View** | Parent auth flow; weekly summary email (SendGrid); progress chart; no raw turn data exposed to parents |
| Month 9 | **Exam Prep Mode** | CBSE Grade 9/10 problem sets; timed practice mode; score prediction from BKT profile |

---

### Production / Startup (Months 10–18)

| Quarter | Milestone | Key Deliverables |
|---|---|---|
| Q4 (M10–12) | **Go-to-Market Readiness** | 5 regional language support; mobile PWA (audio works on Android/iOS); pricing tiers; payment integration (Razorpay) |
| Q4 | **Pilot School Program** | 10 schools, 500 learners; teacher onboarding; support runbook; SLA: 99.5% uptime |
| Q5–6 (M13–18) | **Scale Infrastructure** | Migrate to AWS ECS + RDS + ElastiCache; CDN for TTS audio; auto-scaling; 99.9% SLA |
| Q5–6 | **Offline Packs** | Downloadable subject packs (problems + pre-generated TTS); local SQLite sync; Azure Speech offline model |
| Q5–6 | **B2B / School Integration** | LMS integration (Google Classroom API); bulk student import; admin console; invoicing |

---

## 8. Risk Register

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| **STT accuracy below 85% for accented/vernacular speech** — Indian regional accents (Bihari English, Tamil English, rural Hindi) have high word error rates on standard models | High | High — core product unusable if tutor mishears | (1) Measure WER per accent group in Week 1 pilot. (2) Use Deepgram + Google STT ensemble for low-confidence utterances. (3) Show partial transcript to learner for visual confirmation. (4) Confidence threshold + "say again" fallback. | Engineering |
| **LLM hallucination in mathematical explanations** — Claude generates a plausible-sounding but incorrect hint, misleading learner | Medium | High — damages trust; wrong learning | (1) Problem bank includes worked solution; prompt explicitly provides correct answer and instructs LLM to guide toward it, not away. (2) Add a lightweight answer-checker (sympy for algebra) to verify any numerical claim in the response before TTS. (3) Flag session for human review if correction_cycle > 5. | Engineering + Content |
| **End-to-end latency exceeds 2s** — combined STT + LLM + TTS latency at p95 exceeds natural conversation rhythm | Medium | Medium — poor UX; learners disengage | (1) Sentence-level TTS streaming (primary mitigation). (2) TTS cache for common phrases. (3) Anthropic prompt caching on system prompt. (4) Monitor p95 daily; set 2.5 s alert. (5) Pre-warm AssemblyAI and ElevenLabs connections. | Engineering |
| **Cost per session unsustainable for price-sensitive market** — at ~$0.30/session, charging < ₹100/month (~$1.20) covers only 4 sessions | High | High — business model fails | (1) Negotiate volume pricing with AssemblyAI and Anthropic at 10K+ sessions/month. (2) TTS caching aggressively. (3) Deepgram is no longer the cheaper STT option ($0.59/hr vs. AssemblyAI's $0.45/hr) — reconsider this Phase 3 lever; Llama 3 self-hosted inference remains viable for the LLM leg. (4) B2B school pricing subsidizes B2C learners. | Product + Engineering |
| **Connectivity gaps for rural users** — target market includes users on 2G/poor 3G with intermittent connectivity | High | High — core users excluded | (1) Phase 4 offline packs (pre-downloaded problems + local TTS). (2) Client-side audio buffering + WS reconnect. (3) Graceful text fallback on voice failure. (4) Test on 500 kbps throttled connection in pre-launch QA. | Engineering |
| **Content safety incident for minors** — LLM generates inappropriate content in edge case; or learner uses tutor as chatbot for non-academic purposes | Low | Very High — regulatory, reputational | (1) System prompt hard constraint: refuse non-academic topics. (2) Anthropic safety filters already active. (3) Server-side keyword filter on LLM output before TTS. (4) Audit log of all turn responses retained for 90 days. (5) User reporting button in UI. (6) Parental visibility into session summaries. | Engineering + Legal |
| **AssemblyAI API outage during hackathon demo** — single-provider STT failure during live demo | Low | High — demo failure | (1) Implement Deepgram as hot standby before demo (feature flag). (2) Keep fallback provider credentials active and tested. (3) Prepare pre-recorded session video as last resort backup. | Engineering |

---

*Document end. Version 1.0 — 2026-09-06.*  
*Next review: Phase 2 kickoff (Month 1 post-hackathon).*
