"""
Bridges a client WebSocket connection to AssemblyAI's v3 real-time
streaming API.

Protocol summary
-----------------
Client -> server (this app):
  - binary frames: raw PCM16LE audio, 16kHz mono
  - optional JSON control message: {"type": "terminate"}

Server -> client (this app):
  - JSON passthrough of AssemblyAI's `Begin`, `Turn`, and `Termination`
    messages, verbatim
  - JSON error messages of the shape {"type": "error", "detail": "..."}
    for local failures (missing/invalid API key, upstream connection
    problems, etc.)
"""

import json
import logging
import os
from typing import Callable, Coroutine, Optional

import websockets
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState
from websockets.exceptions import ConnectionClosed, InvalidStatus

logger = logging.getLogger(__name__)

ASSEMBLYAI_STREAMING_URL = (
    "wss://streaming.assemblyai.com/v3/ws"
    "?sample_rate=16000&speech_model=universal-3-5-pro&format_turns=true"
)


async def _send_error(client_ws: WebSocket, detail: str) -> None:
    """Send a JSON error message to the client, if the socket is still open."""
    if client_ws.application_state == WebSocketState.CONNECTED:
        try:
            await client_ws.send_json({"type": "error", "detail": detail})
        except Exception:
            logger.exception("Failed to send error message to client")


async def run_bridge(
    client_ws: WebSocket,
    on_turn: Optional[Callable[[str], Coroutine]] = None,
) -> None:
    """
    Accept an already-open client WebSocket, open a matching connection to
    AssemblyAI's streaming API, and pump data between the two until either
    side disconnects or the client asks to terminate.
    """
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        await _send_error(client_ws, "Server is missing ASSEMBLYAI_API_KEY.")
        await client_ws.close(code=1011)
        return

    try:
        async with websockets.connect(
            ASSEMBLYAI_STREAMING_URL,
            additional_headers={"Authorization": api_key},
            max_size=16 * 1024 * 1024,
        ) as aai_ws:
            # AssemblyAI sends a "Begin" message as soon as the session opens.
            begin_raw = await aai_ws.recv()
            begin_msg = json.loads(begin_raw)
            if begin_msg.get("type") != "Begin":
                await _send_error(
                    client_ws,
                    "AssemblyAI rejected the session: "
                    + begin_msg.get("error", "unknown error"),
                )
                await _close_client(client_ws, code=1008)
                return
            await client_ws.send_json(begin_msg)

            await _pump(client_ws, aai_ws, on_turn=on_turn)

    except InvalidStatus as exc:
        # Handshake was rejected outright, e.g. bad/missing API key.
        status = getattr(exc.response, "status_code", None)
        logger.warning("AssemblyAI rejected the connection (status=%s)", status)
        await _send_error(
            client_ws,
            "AssemblyAI authentication failed. Check the server's API key.",
        )
        await _close_client(client_ws, code=1008)

    except ConnectionClosed as exc:
        if exc.rcvd is not None and exc.rcvd.code == 1008:
            logger.warning("AssemblyAI closed the connection: UNAUTHORIZED")
            await _send_error(
                client_ws,
                "AssemblyAI authentication failed. Check the server's API key.",
            )
            await _close_client(client_ws, code=1008)
        else:
            logger.info("AssemblyAI connection closed: %s", exc)
            await _close_client(client_ws)

    except WebSocketDisconnect:
        # Client went away before we ever finished setting things up.
        pass

    except Exception:
        logger.exception("Unexpected error in AssemblyAI bridge")
        await _send_error(client_ws, "Internal server error in audio pipeline.")
        await _close_client(client_ws, code=1011)


async def _pump(
    client_ws: WebSocket,
    aai_ws,
    on_turn: Optional[Callable[[str], Coroutine]] = None,
) -> None:
    """Relay messages between the client and AssemblyAI until one side stops."""
    import asyncio

    async def client_to_aai():
        while True:
            message = await client_ws.receive()

            if message["type"] == "websocket.disconnect":
                return

            if "bytes" in message and message["bytes"] is not None:
                await aai_ws.send(message["bytes"])
                continue

            if "text" in message and message["text"] is not None:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "terminate":
                    await aai_ws.send(json.dumps({"type": "Terminate"}))
                    return

    async def aai_to_client():
        async for raw in aai_ws:
            msg = json.loads(raw)
            await client_ws.send_json(msg)
            if msg.get("type") == "Turn" and msg.get("end_of_turn") is True:
                if on_turn is not None:
                    turn_text = msg.get("transcript", "")
                    await on_turn(turn_text)
            if msg.get("type") == "Termination":
                return

    client_task = asyncio.create_task(client_to_aai())
    aai_task = asyncio.create_task(aai_to_client())

    try:
        done, pending = await asyncio.wait(
            {client_task, aai_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if client_task in done and aai_task in pending:
            # client_to_aai finished (client sent terminate or disconnected);
            # give AssemblyAI up to 5 s to drain final Turn/Termination messages.
            try:
                await asyncio.wait_for(aai_task, timeout=5.0)
            except asyncio.TimeoutError:
                aai_task.cancel()
        else:
            for task in pending:
                task.cancel()
        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, (ConnectionClosed, WebSocketDisconnect)):
                raise exc
    finally:
        # Always tell AssemblyAI we're done so it stops billing the session,
        # unless the client_to_aai loop already sent Terminate.
        try:
            await aai_ws.send(json.dumps({"type": "Terminate"}))
        except Exception:
            pass
        await _close_client(client_ws)


async def _close_client(client_ws: WebSocket, code: int = 1000) -> None:
    if client_ws.application_state == WebSocketState.CONNECTED:
        try:
            await client_ws.close(code=code)
        except Exception:
            pass
