from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.websocket.manager import manager
import json

router = APIRouter()

@router.websocket("/ws/mod")
async def mod_websocket(
    websocket: WebSocket,
    server_id: str = Query(...),
    token: str = Query(...)
):
    connected = await manager.connect(websocket, server_id, token)
    if not connected:
        return

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await manager.handle_message(server_id, message)
    except WebSocketDisconnect:
        manager.disconnect(server_id)
    except Exception as e:
        print(f"WebSocket error for {server_id}: {e}")
        manager.disconnect(server_id)
