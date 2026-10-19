# Product Requirements Document
## A Voice-First Tutoring Companion

**Owners:** Varshini and Vaasini
**Category:** Voice / Realtime / AI / Agent / EdTech
**Document status:** Draft for internal alignment
**Version:** 2.0 — expands the original hackathon MVP into a full business PRD; original MVP scope retained and reorganized as Appendix A

---

## 1. Executive Summary

Millions of students want to learn but hit a wall that has nothing to do with intelligence: no one at home who can explain the concept, no teacher who has time for their specific confusion, and no comfortable way to ask a "stupid question" out loud without being typed at by a chatbot that expects perfect spelling and phrasing.

This product is a voice-first AI tutor — not a chatbot with a microphone bolted on, but a system built from the ground up around spoken, real-time, Socratic conversation. The learner talks through their reasoning; the tutor listens, diagnoses the specific misconception, and responds the way a good human tutor would — with a question, a hint, or a smaller sub-problem — rather than an answer key.

We are targeting the segment of learners existing AI tutors serve worst: first-generation learners with no home academic support, students who struggle with reading/writing-heavy interfaces because of dyslexia or similar disabilities, and vernacular/regional-language speakers for whom English-first, text-first tools are a second barrier stacked on top of the first.

---

## 2. Problem Statement

### 2.1 The core problem
Most digital tutoring — including most "AI tutors" — is built around typing, reading, and static question-answer flows. Learning by explaining your reasoning out loud, being challenged conversationally, and correcting a misconception in real time is how people actually build understanding, but text-first interfaces make this slow, unnatural, and exclusionary for a large share of learners.

### 2.2 Who this actually hurts
This is not a generic "students need help" problem. It is sharpest for three overlapping groups:

**First-generation learners.** Research on first-generation learners (FGLs) across India and other developing-country contexts (Young Lives survey data covering Ethiopia, India, Peru, and Vietnam) shows consistent, significant learning gaps driven largely by an inability to get homework help at home and lower household academic stimulation. In India specifically, government reports have flagged that a large share of students are first-generation learners, and this population is disproportionately represented among dropouts. A text-based tutor still assumes a baseline of comfortable reading, typing, and self-directed navigation that mirrors the same literacy/schooling advantage FGLs lack — it does not remove the barrier, it relocates it.

**Students with reading- and writing-related disabilities.** For students with dyslexia, dysgraphia, or ADHD, typing and reading dense chat interfaces is itself a tax before any learning happens. The assistive-technology literature is explicit that text-to-speech and speech-to-text tools reduce the decoding/writing burden and let these students focus on comprehension and reasoning rather than mechanics. Most "AI tutors" treat voice as an accessibility bolt-on (playback of a chat) rather than the primary interface.

**Vernacular / regional-language learners.** A large share of India's population is more comfortable speaking than typing in their home language, and rural/semi-urban learners are exactly where teacher shortages and content scarcity in regional languages are worst. Voice removes the literacy and typing burden in a way text-first tools structurally cannot.

### 2.3 Why this hasn't been solved yet
Two things had to become good enough at the same time for a real voice-first Socratic tutor to work: low-latency streaming speech-to-text/text-to-speech, and language models capable of evaluating spoken reasoning (not just matching a final answer) and choosing a pedagogically appropriate next move. Both only became reliable and affordable recently. Most incumbent products were designed in the text-chat era and have voice added on top rather than built around it.

---

## 3. Market Research

### 3.1 Market size and growth
- The global AI tutors market is estimated at roughly **$2.1–3.7B in 2025**, with multiple analysts projecting growth to **$6.5–18.9B by the early-to-mid 2030s** (CAGR estimates ranging ~20–30% depending on the research firm and market definition).
- India's AI-in-education market alone is estimated to exceed **$2.8B**, driven partly by the National Education Policy's mandate for AI integration by 2030.
- **Language learning and vernacular/conversational AI tutoring are called out as the fastest-growing sub-segments**, ahead of the broader market average — directly relevant to a voice-first, multilingual product.
- Funding and government programs (India's NEP AI mandate, Canada's CanCode, Germany's Digitalpakt 2.0) are increasingly directed specifically at underserved-learner access, which is a channel and positioning opportunity, not just a market-size statistic.

### 3.2 The equity gap is large and well-documented, not anecdotal
- Research across India, Ethiopia, Peru, and Vietnam finds first-generation learners face measurable, persistent learning gaps tied specifically to lack of homework support at home — the exact gap a Socratic voice tutor is designed to fill outside school hours.
- Market analyses of AI tutoring explicitly flag that **rural and low-income access remains capped below ~20% penetration** despite proven efficacy elsewhere, mainly due to connectivity and content-language gaps — this is the addressable underserved segment, not a footnote.
- On the disability side, an estimated **5–20% of any student population has dyslexia**, and the assistive-technology research base consistently shows voice interfaces measurably reduce the "mechanics tax" (reading/typing) so students can spend cognitive effort on the actual subject.

### 3.3 Competitive landscape

| Player | What they do | Where they fall short for our target user |
|---|---|---|
| **Khanmigo (Khan Academy)** | Socratic-style AI tutor, strong pedagogy, tied to Khan Academy's content library; has TTS/STT as a feature | Fundamentally **text-first** — conversations are typed and read, with voice as an add-on, not the interface. No dedicated app. Tied entirely to Khan Academy's own content, so it doesn't work for other curricula. Real-time voice conversation (interruption, natural turn-taking) is explicitly a gap reviewers call out as of 2026. |
| **ChatGPT / general LLM assistants** | Broad, flexible, capable of voice mode | Not built around Socratic pedagogy by default — tends toward direct answers unless heavily prompted; no persistent lesson state, misconception tracking, or bounded curriculum; no parental/teacher visibility; general-purpose safety guardrails, not education-specific ones. |
| **HeyOtto and similar child-safe AI companions** | Parent-provisioned, voice-capable, good for kids with ADHD/dyslexia/autism traits | Positioned as a broad assistant/companion, not a subject-mastery tutor with structured lesson state, difficulty adaptation, or mastery tracking. |
| **edVerse, Anvesh.AI, Swavid and similar India-focused voice/vernacular tutors** | Voice-first or vernacular-first, some offline-capable, targeting rural/regional-language students directly; edVerse reports large-scale rural deployment and measurable grade-level gains | This is the closest competitive set and validates the thesis — but from available information, these tend to emphasize **content delivery and doubt-solving** (explain a concept, solve a photographed problem) more than **reasoning-aware, Socratic evaluation of the learner's own spoken explanation**. None of the public descriptions emphasize diagnosing *how* a learner is reasoning and choosing the minimal pedagogical intervention — they emphasize answering and explaining. |

### 3.4 The gap in the market
No major player currently combines all three of:
1. **Voice as the primary interface** (not chat with playback), with real-time turn-taking and interruption handling.
2. **Reasoning-aware Socratic evaluation** — assessing *how* the learner is thinking, not just whether their final answer matches, and choosing the smallest useful intervention (acknowledge, probe, hint, counterexample, simpler subproblem, correction, challenge) rather than defaulting to an explanation.
3. **Built for the underserved learner from day one** — vernacular/multilingual by design, low reliance on reading/typing fluency, and priced/designed for the first-gen and low-connectivity segment rather than retrofitted onto an urban/English-first product.

**This is the wedge.**

---

## 4. Target Users & Personas

### 4.1 Primary persona — "Meena," the first-generation learner
Grade 8–10 student, government or low-fee private school, first in her family to study past secondary school. Parents are supportive but cannot check her math homework or explain a concept she got wrong. She has a basic smartphone and prefers speaking in her home language over typing in English. She doesn't lack ability — she lacks a second explanation when the first one (from a rushed classroom) didn't land.

### 4.2 Secondary persona — "Arjun," the learner with a reading-related disability
Middle or high school student with dyslexia or ADHD. Typing and reading long chat responses is fatiguing and slows him down before he even gets to the subject matter. He understands concepts well when he can talk them through, but conventional interfaces penalize him for a reading/writing difficulty that has nothing to do with his grasp of the material.

### 4.3 Tertiary persona — "Priya," the self-directed exam candidate
Preparing for competitive/interview-style assessments, often multitasking (commuting, working) and wants a conversational practice partner that challenges her reasoning rather than a static question bank.

*(All three personas are illustrative; the hackathon MVP demo will use a bounded math/science version of persona 1 as the primary showcase — see Appendix A.)*

---

## 5. Product Vision & Differentiator

**Vision:** Become a voice-first learning companion that tutors, challenges, and coaches — reaching learners that text-first, urban-first, English-first EdTech structurally excludes.

**Core differentiator:** The tutor evaluates *how the learner is reasoning*, not just their final answer, and chooses the smallest pedagogically useful next move instead of defaulting to giving an explanation. Voice is not a convenience layer on top of a chatbot — it is the interface the whole product is designed around, which is what makes it usable for learners who struggle with text-first tools for reasons of language, literacy, or disability.

### 5.1 Non-goals (for now)
- Not attempting all subjects at once — start bounded and expand deliberately.
- Not building unrestricted general-knowledge tutoring — content stays inside a verified problem bank to control hallucination risk.
- Not building long-term student profiling or fully autonomous curriculum design in the MVP.

---

## 6. Success Metrics (Product-level, business-facing)

- **Learning outcome signal:** measurable improvement in concept mastery / correction-cycle completion (baseline vs. after N sessions) — comparable metrics reported by adjacent products (e.g., reported grade-level gains from rural voice-tutor deployments) should inform our own evaluation design.
- **Accessibility reach:** % of active users who are first-gen learners, vernacular-primary, or disclose a reading/writing-related learning difference (self-reported, opt-in).
- **Engagement quality over vanity metrics:** completion of full correction cycles (wrong → hinted → corrected) rather than raw session counts, since the pedagogical model's core promise is reasoning correction, not just usage.
- **Latency/UX bar:** response latency low enough for natural spoken turn-taking (see Appendix A for MVP-level targets).
- **Cost per learner:** given the target segment's price sensitivity, unit economics (STT/TTS/LLM inference cost per session) need to be tracked from day one, not bolted on later — this directly affects whether the product can serve the underserved segment at a sustainable price point.

---

## 7. Roadmap

### Phase 1 — MVP (bounded subject, voice-first Socratic loop)
See **Appendix A** for full detail. Single subject (math/science), core voice loop, reasoning-based hinting, session summary, vernacular shown as a must-have wherever feasible even at MVP stage.

### Phase 2 — Adaptive tutor
- Expand beyond one subject into a small set of verified subject modules.
- Persistent learner model: skill mastery, misconceptions, confidence, preferred teaching style.
- Full multilingual/vernacular tutoring while retaining the same lesson state.
- Detect hesitation, uncertainty, and confusion from conversational behavior as supplementary signals.
- Proactive revision sessions based on demonstrated weaknesses.

### Phase 3 — Multimodal learning agent
- Camera input for handwritten work, diagrams, textbook pages, physical demonstrations.
- Visual explanations/whiteboards alongside voice.
- Seamless switching between voice, text, camera, and visual interaction.
- Curriculum planning and goal-based lesson sequencing.
- Teacher/parent views focused on progress and misconceptions, not raw transcripts.

### Long-term / startup vision
- Exam preparation, interview practice, language learning, and professional upskilling as distinct tutor modes.
- Peer/debate simulation and role-play agents for communication-heavy learning.
- Low-connectivity/offline lesson packs — directly addressing the rural/low-bandwidth access gap identified in market research (Section 3.2).

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| STT errors, especially for accented or vernacular speech | Confirmation/rephrase prompts when transcription confidence is low; invest early in vernacular STT accuracy given it's core to the differentiator, not a nice-to-have |
| Tutor is too verbose, breaks natural turn-taking | Enforced short-turn response policy |
| Hallucinated explanations outside the verified content | Bounded curriculum/problem bank at MVP; clearly label anything generated outside it |
| Latency breaks the "natural conversation" promise | Streaming responses, concise turns, partial transcripts for UI feedback only (see Appendix A) |
| Underserved target segment has low ability/willingness to pay | Explore institutional, CSR, or government-subsidized channels (NEP AI mandate, state programs) alongside or instead of direct-to-consumer pricing |
| Connectivity gaps in the exact population we're targeting | Offline/low-bandwidth mode is on the roadmap (Phase 3+) but should be evaluated for earlier prioritization given how central it is to reaching rural users |

---

## Appendix A — MVP / Hackathon Build Spec

*(Retained and lightly reorganized from the original technical draft. This is the buildable slice used for the hackathon demo and Phase 1 engineering.)*

### A.1 Hackathon use case
A realtime math/science tutor. The learner chooses a topic, explains an answer aloud, gets challenged with Socratic follow-ups, and receives a short end-of-session mastery summary.

### A.2 Core user journey
1. Choose topic.
2. Tutor gives a problem verbally.
3. Learner explains reasoning.
4. Realtime STT captures the explanation.
5. Tutor evaluates reasoning, not only the final answer.
6. Tutor asks a targeted follow-up.
7. Learner revises.
8. Tutor adapts difficulty.
9. Session ends with strengths, misconceptions, and next exercise.

### A.3 MVP features
Realtime voice input; low-latency tutor response; lesson state; problem generation from a bounded bank; reasoning assessment; Socratic hints; adaptive difficulty; interruption/turn handling; session summary.

### A.4 Demo script
Tutor: *"Explain how you would solve 2x + 6 = 14."* Learner explains incorrectly. Tutor identifies the specific misconception and asks a smaller question. Learner corrects it. Tutor increases difficulty with a related problem. At the end, the tutor states what the learner understood, where they struggled, and what to practice next.

### A.5 Success metrics (MVP-level, technical)
- Tutor response latency acceptable for natural turn-taking.
- ≥85% correct classification of scripted reasoning states.
- ≥80% of test cases use a hint/question rather than a premature answer reveal.
- Learner completes at least one correction cycle.

### A.6 Architecture
Microphone → AssemblyAI realtime STT → turn manager → learner-state store → tutor orchestrator → content/problem bank + reasoning evaluator → response policy → TTS → learner.

### A.7 Core components
Realtime audio client; STT stream; turn-taking manager; conversation/session state; curriculum/problem bank; reasoning evaluator; tutor policy; TTS; telemetry.

### A.8 Data contracts
- **TranscriptEvent:** `{text, is_final, timestamp, confidence}`
- **LearnerState:** `{topic, level, mastery_by_skill, misconceptions, current_problem, attempt_count}`
- **TutorDecision:** `{goal, strategy, prompt, difficulty_change}`
- **SessionSummary:** `{strengths, misconceptions, next_steps}`

### A.9 Pedagogical loop
Problem → learner explanation → reasoning classification → choose next move. Possible moves: acknowledge, probe, hint, counterexample, simpler subproblem, correction, challenge, recap. The tutor should prefer the smallest intervention that moves the learner forward.

### A.10 Tooling
- **Frontend:** React/Next.js
- **Realtime STT:** AssemblyAI streaming
- **Backend:** FastAPI/Node
- **LLM:** chosen model for reasoning/tutor policy
- **TTS:** browser/native or selected TTS API
- **State:** SQLite/JSON for MVP

### A.11 Realtime design
Use partial transcripts for UI feedback but trigger pedagogical decisions on stable turns. Keep responses short. Allow barge-in so the learner can interrupt a long answer.

### A.12 Adaptation
Maintain explicit state rather than relying only on chat history. Track skill, misconception, confidence, and recent attempts. Difficulty changes should be deterministic and explainable for the demo.

### A.13 Content safety/quality
Use a bounded curriculum and verified problem bank. For factual explanations outside the bank, clearly label AI-generated explanations and keep the MVP domain narrow.

### A.14 Test plan
Test STT transcript handling, turn boundaries, reasoning labels, tutor strategy selection, difficulty transitions, interruption, and end-to-end lesson completion.

### A.15 Deployment
Single frontend/backend deployment with deterministic content. Keep API keys server-side; use temporary tokens for browser streaming where supported.

---

## Sources consulted for market research (Section 3)
- Grand View Research — AI Tutors Market Size, Share & Trends Report, 2026–2033
- Mordor Intelligence — AI Tutors Market Size, Share & 2030 Growth Trends Report
- Intel Market Research — AI Tutoring Platform Market Outlook 2026–2034; AI Education Tools Market Outlook 2026–2034
- Tutorbase — EdTech & AI in Education Statistics 2026
- EERA / Springer / ResearchGate — First-generation learner research (India, Ethiopia, Peru, Vietnam; Young Lives survey data)
- GEM Report SCOPE — First-generation students research
- International Dyslexia Association; Lexia; LDRFA — Assistive technology and TTS/STT research for dyslexia/ADHD
- MyEngineeringBuddy, AITeacherHacks, KidsAITools — Khanmigo reviews (2026)
- HeyOtto — Best AI for Kids 2026 comparison
- Neural Brief — edVerse rural voice AI tutor deployment
- Anvesh.AI, Swavid, IBEF — India vernacular/voice-first tutoring landscape
