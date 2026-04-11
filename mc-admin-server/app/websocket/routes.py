from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.websocket.manager import manager
import json
import logging

logger = logging.getLogger(__name__)

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
        logger.info(f"WebSocket disconnected for {server_id}")
        await manager.disconnect(server_id)
    except Exception as e:
        logger.error(f"WebSocket error for {server_id}: {e}", exc_info=True)
        await manager.disconnect(server_id)
