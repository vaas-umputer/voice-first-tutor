from fastapi import WebSocket
from starlette.websockets import WebSocketState


async def send_tutor_turn(client_ws: WebSocket, text: str) -> None:
    """Send tutor response text to the browser for client-side TTS via speechSynthesis."""
    if client_ws.application_state == WebSocketState.CONNECTED:
        try:
            await client_ws.send_json({"type": "tutor_turn", "text": text})
        except Exception:
            pass
