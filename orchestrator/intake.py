"""
Intake module — handles the learner's first message before the tutoring loop starts.

The learner reaches out with what they're struggling with. This module:
  1. Figures out the topic and difficulty level from what they said
  2. Picks a matching problem from the bank
  3. Returns a warm opening response that acknowledges what they said

No tutoring logic here — just onboarding.
"""

from __future__ import annotations

import os
import json
import time
from typing import Tuple

from .problem_bank import select_for_level

INTAKE_SYSTEM_PROMPT = """You are Priya, a warm AI math tutor.
A student has just reached out to you for help. Your job is to figure out:
1. What topic they need help with (pick from the list below)
2. How difficult the work seems (easy / medium / hard)
3. Write a short warm opening response that acknowledges what they said and invites them to share more or start working.

Available topics:
  math.ratio.speed_distance_time — speed, distance, time, average speed, km/h

If the topic is unclear, default to math.ratio.speed_distance_time.
If the difficulty is unclear, default to easy.

IMPORTANT: Write the `response` field in the SAME language the learner used.
If they wrote in Hindi or Hinglish, respond in Hindi. Keep mathematical terms (speed, distance, km/h) in English regardless.

Return ONLY valid JSON:
{"topic": "...", "level": "easy|medium|hard", "response": "your warm opening response (max 30 words, end with ?)"}

EXAMPLES:
Utterance: "I'm stuck on a speed problem"
{"topic": "math.ratio.speed_distance_time", "level": "easy", "response": "Of course! Speed problems can be tricky. What does the problem ask you to find?"}

Utterance: "my homework has trains going different speeds and I don't get it"
{"topic": "math.ratio.speed_distance_time", "level": "medium", "response": "Train problems are classic! Can you tell me what information the problem gives you?"}

Utterance: "mujhe speed aur distance wale sawaal mein help chahiye"
{"topic": "math.ratio.speed_distance_time", "level": "easy", "response": "Bilkul! Speed aur distance ke sawaal thode tricky hote hain. Aapka sawaal kya hai?"}

Utterance: "I need help with maths"
{"topic": "math.ratio.speed_distance_time", "level": "easy", "response": "Happy to help! What topic or problem are you working on right now?"}
"""

_HINDI_KEYWORDS = [
    "speed", "distance", "time", "km", "ghanta", "train", "gaadi",
    "sawaal", "help", "samajh", "nahi", "mujhe", "chahiye", "kaise",
    "kitna", "dum", "tez", "dhima",
]

_HINDI_OPENINGS = {
    "speed": "Speed aur distance ke sawaal — saath milke karte hain. Sawaal mein kya puchha gaya hai?",
    "stuck": "Koi baat nahi! Yahi toh main hoon. Kaun sa topic problem de raha hai?",
    "default": "Bilkul help karunga! Aap kaunsa sawaal ya topic samajhna chahte hain?",
}


async def handle(first_message: str, language: str = "en") -> Tuple[str, str, str, str]:
    """
    Process the learner's first message.

    Returns (topic, level, problem_id, opening_response).
    """
    backend = os.environ.get("TUTOR_LLM_BACKEND", "").lower()

    if backend == "ollama":
        result = await _via_ollama(first_message)
    elif backend == "anthropic" or (not backend and os.environ.get("ANTHROPIC_API_KEY")):
        result = await _via_anthropic(first_message)
    else:
        result = _via_mock(first_message, language=language)

    topic, level, opening = result
    problem = select_for_level(level)
    return topic, level, problem.id, opening


async def _via_ollama(message: str) -> Tuple[str, str, str]:
    try:
        import ollama as _ollama
        model = os.environ.get("OLLAMA_MODEL", "llama3.2")
        response = await _ollama.AsyncClient().chat(
            model=model,
            format="json",
            messages=[
                {"role": "system", "content": INTAKE_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
        )
        data = json.loads(response.message.content)
        return data["topic"], data["level"], data["response"]
    except Exception:
        return _via_mock(message)


async def _via_anthropic(message: str) -> Tuple[str, str, str]:
    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic()
        msg = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            system=INTAKE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message}],
        )
        data = json.loads(msg.content[0].text)
        return data["topic"], data["level"], data["response"]
    except Exception:
        return _via_mock(message)


def _via_mock(message: str, language: str = "en") -> Tuple[str, str, str]:
    text = message.lower()
    level = "easy"
    if any(w in text for w in ["hard", "difficult", "challenging", "tricky", "two trains", "relative", "mushkil", "kathin"]):
        level = "medium"

    if language == "hi":
        if any(w in text for w in ["speed", "distance", "time", "km", "ghanta", "train", "gaadi", "tez", "dhima"]):
            opening = _HINDI_OPENINGS["speed"]
        elif any(w in text for w in ["samajh", "nahi", "stuck", "help", "chahiye"]):
            opening = _HINDI_OPENINGS["stuck"]
        else:
            opening = _HINDI_OPENINGS["default"]
    else:
        if any(w in text for w in ["speed", "distance", "time", "km", "hour", "train", "car", "fast"]):
            opening = "Speed problems — let's work through it together. What does your problem ask you to find?"
        elif any(w in text for w in ["don't understand", "confused", "stuck", "help"]):
            opening = "No worries, that's what I'm here for! What topic is giving you trouble?"
        else:
            opening = "Happy to help! Can you share the problem you're working on, or tell me what part is confusing you?"

    return "math.ratio.speed_distance_time", level, opening
