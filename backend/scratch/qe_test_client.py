"""
QE test client for the /ws/session audio pipeline endpoint.

Usage:
    python qe_test_client.py <wav_path> [--url ws://localhost:8000/ws/session] [--no-audio]

Reads a 16kHz mono 16-bit PCM WAV file, strips the WAV header, and streams
the raw PCM16 data to the server in small chunks with pacing to roughly
simulate real-time audio. Collects every JSON message received, then sends
{"type": "terminate"} and waits for a Termination message (with timeout).

Prints a clear trace of what happened.
"""

import argparse
import asyncio
import json
import sys
import time
import wave

import websockets


def load_pcm16(wav_path: str) -> bytes:
    with wave.open(wav_path, "rb") as wf:
        assert wf.getframerate() == 16000, f"expected 16kHz, got {wf.getframerate()}"
        assert wf.getnchannels() == 1, f"expected mono, got {wf.getnchannels()} channels"
        assert wf.getsampwidth() == 2, f"expected 16-bit, got {wf.getsampwidth()*8}-bit"
        return wf.readframes(wf.getnframes())


async def run_test(wav_path: str, url: str, send_audio: bool = True, label: str = "") -> dict:
    result = {
        "label": label,
        "begin": None,
        "turns": [],
        "final_transcript": None,
        "termination": None,
        "errors": [],
        "close_info": None,
    }

    print(f"\n=== Test: {label} ===")
    print(f"Connecting to {url} ...")

    messages = []
    recv_done = asyncio.Event()

    async def receiver(ws):
        try:
            async for raw in ws:
                msg = json.loads(raw)
                messages.append(msg)
                mtype = msg.get("type")
                if mtype == "Begin":
                    result["begin"] = msg
                    print(f"  <- Begin: {msg}")
                elif mtype == "Turn":
                    result["turns"].append(msg)
                    eot = msg.get("end_of_turn")
                    transcript = msg.get("transcript")
                    print(f"  <- Turn (end_of_turn={eot}): {transcript!r}")
                    if eot:
                        result["final_transcript"] = transcript
                elif mtype == "Termination":
                    result["termination"] = msg
                    print(f"  <- Termination: {msg}")
                elif mtype == "error":
                    result["errors"].append(msg)
                    print(f"  <- ERROR: {msg}")
                else:
                    print(f"  <- Other: {msg}")
        except websockets.exceptions.ConnectionClosed as exc:
            result["close_info"] = f"closed code={exc.code} reason={exc.reason!r}"
            print(f"  -- connection closed: {result['close_info']}")
        finally:
            recv_done.set()

    try:
        async with websockets.connect(url, max_size=16 * 1024 * 1024) as ws:
            recv_task = asyncio.create_task(receiver(ws))

            if send_audio:
                pcm = load_pcm16(wav_path)
                # ~100ms per chunk at 16kHz, 16-bit mono = 3200 bytes/chunk
                chunk_size = 3200
                n_chunks = 0
                for i in range(0, len(pcm), chunk_size):
                    chunk = pcm[i : i + chunk_size]
                    await ws.send(chunk)
                    n_chunks += 1
                    await asyncio.sleep(0.1)
                print(f"  -> sent {n_chunks} audio chunks ({len(pcm)} bytes total)")
                # Give the server/AssemblyAI a moment to catch up on final turns
                await asyncio.sleep(2.0)
            else:
                print("  -> (no audio sent)")

            print("  -> sending terminate")
            await ws.send(json.dumps({"type": "terminate"}))

            try:
                await asyncio.wait_for(recv_done.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                print("  !! TIMEOUT waiting for connection close / Termination after terminate")
                recv_task.cancel()

    except Exception as exc:
        print(f"  !! Exception during test: {exc!r}")
        result["errors"].append({"type": "client_exception", "detail": repr(exc)})

    print(f"--- Summary for {label} ---")
    print(f"  Begin received: {result['begin'] is not None}")
    print(f"  Turn messages: {len(result['turns'])}")
    print(f"  Final transcript: {result['final_transcript']!r}")
    print(f"  Termination received: {result['termination'] is not None}")
    print(f"  Errors: {result['errors']}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("wav_path", nargs="?", default=None)
    parser.add_argument("--url", default="ws://localhost:8000/ws/session")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    label = args.label or (args.wav_path or "no-audio")
    res = asyncio.run(
        run_test(args.wav_path, args.url, send_audio=not args.no_audio, label=label)
    )
