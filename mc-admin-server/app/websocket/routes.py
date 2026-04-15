from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
from app.websocket.manager import manager
import json
import re
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# server_id 格式：字母、数字、下划线、连字符，1-64字符
_VALID_SERVER_ID = re.compile(r'^[a-zA-Z0-9_\-]{1,64}$')

# WebSocket 单条消息最大大小（100KB）
_MAX_WS_MESSAGE_SIZE = 100 * 1024

# 合法的消息类型
_VALID_MESSAGE_TYPES = {"status", "result"}


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

    # 校验 server_id 格式
    if not _VALID_SERVER_ID.match(server_id):
        await websocket.close(code=1008, reason="Invalid server_id format")
        return

    connected = await manager.connect(websocket, server_id, token)
    if not connected:
        return

    try:
        while True:
            data = await websocket.receive_text()

            # 消息大小限制
            if len(data) > _MAX_WS_MESSAGE_SIZE:
                logger.warning(f"WebSocket消息过大 ({len(data)} bytes) from {server_id}")
                continue

            # JSON解析
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"WebSocket收到无效JSON from {server_id}")
                continue

            # 消息格式校验
            if not isinstance(message, dict) or "type" not in message:
                logger.warning(f"WebSocket消息缺少type字段 from {server_id}")
                continue

            # 消息类型白名单
            if message.get("type") not in _VALID_MESSAGE_TYPES:
                logger.warning(f"WebSocket收到未知消息类型 '{message.get('type')}' from {server_id}")
                continue

            await manager.handle_message(server_id, message)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {server_id}")
        await manager.disconnect(server_id)
    except Exception as e:
        logger.error(f"WebSocket error for {server_id}: {e}", exc_info=True)
        await manager.disconnect(server_id)
