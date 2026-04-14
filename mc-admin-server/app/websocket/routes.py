from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
from app.websocket.manager import manager
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws/mod")
async def mod_websocket(
    websocket: WebSocket,
    server_id: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
):
    # 优先从Header读取认证信息（更安全），兼容旧版query param方式
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
    if not server_id:
        server_id = websocket.headers.get("x-server-id", "").strip()

    if not server_id or not token:
        await websocket.close(code=1008, reason="Missing credentials")
        return

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
