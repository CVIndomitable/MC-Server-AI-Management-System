from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
from app.websocket.manager import manager
from app.core.permissions import require_server_access
from config.settings import settings
from jose import JWTError, jwt
import json
import re
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# server_id 格式：字母、数字、下划线、连字符，1-64字符
_VALID_SERVER_ID = re.compile(r'^[a-zA-Z0-9_\-]{1,64}$')

# WebSocket 单条消息最大大小（100KB）
_MAX_WS_MESSAGE_SIZE = 100 * 1024

# 合法的消息类型（来自模组侧）
_VALID_MESSAGE_TYPES = {
    "status", "result", "ai_chat_request", "confirm_required", "ping", "async_event"
}


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

            # 消息大小限制：直接关闭连接，避免被恶意客户端持续发送大包耗资源
            if len(data) > _MAX_WS_MESSAGE_SIZE:
                logger.warning(f"WebSocket消息过大 ({len(data)} bytes) from {server_id}，关闭连接")
                await websocket.close(code=1009, reason="Message too big")
                await manager.disconnect(server_id)
                return

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


@router.websocket("/ws/client")
async def client_websocket(
    websocket: WebSocket,
    server_id: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
):
    """前端订阅异步推送（Spark 采样报告、其他后台事件等）。
    鉴权走 JWT（与 HTTP API 同源），按 (admin_id, server_id) 建立 1:1 订阅。
    消息方向：主要是 server → client；client 偶尔发 ping 保活。
    """
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
    if not server_id:
        server_id = websocket.headers.get("x-server-id", "").strip()

    if not server_id or not token:
        await websocket.close(code=1008, reason="Missing credentials")
        return

    if not _VALID_SERVER_ID.match(server_id):
        await websocket.close(code=1008, reason="Invalid server_id format")
        return

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError:
        await websocket.close(code=1008, reason="Invalid token")
        return

    admin_id = payload.get("sub")
    if not admin_id:
        await websocket.close(code=1008, reason="Invalid token payload")
        return

    try:
        await require_server_access(admin_id, server_id, min_role="admin")
    except Exception as e:
        logger.info(f"/ws/client 权限校验失败 admin={admin_id} server={server_id}: {e}")
        await websocket.close(code=1008, reason="Forbidden")
        return

    await websocket.accept()
    await manager.register_client(websocket, admin_id, server_id)
    # 握手确认（前端已有 auth_response 分支会据此清空鉴权超时）
    try:
        await websocket.send_text(json.dumps({
            "type": "auth_response",
            "server_id": server_id,
        }))
    except Exception:
        pass

    try:
        while True:
            data = await websocket.receive_text()
            if len(data) > _MAX_WS_MESSAGE_SIZE:
                await websocket.close(code=1009, reason="Message too big")
                break
            # 客户端目前只需要 ping 保活；其余消息静默忽略
            try:
                msg = json.loads(data)
                if isinstance(msg, dict) and msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                continue
    except WebSocketDisconnect:
        logger.info(f"/ws/client disconnected admin={admin_id} server={server_id}")
    except Exception as e:
        logger.error(f"/ws/client error admin={admin_id} server={server_id}: {e}", exc_info=True)
    finally:
        await manager.unregister_client(admin_id, server_id, websocket)
