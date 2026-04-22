"""
WebSocket 聊天管理器：处理客户端 ↔ AI 的流式对话
"""
from fastapi import WebSocket
from typing import Dict, Optional
import json
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ChatConnectionManager:
    def __init__(self):
        # key: (admin_id, server_id), value: WebSocket
        self.active_connections: Dict[tuple, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, admin_id: str, server_id: str) -> bool:
        """建立聊天 WebSocket 连接"""
        key = (admin_id, server_id)

        # 同一用户+服务器只允许一个连接（新连接踢掉旧连接）
        async with self._lock:
            if key in self.active_connections:
                old_ws = self.active_connections[key]
                try:
                    await old_ws.close(code=1000, reason="New connection established")
                except Exception:
                    pass
                logger.info(f"聊天WS: 用户 {admin_id} 的旧连接已被新连接替换")

            self.active_connections[key] = websocket

        await websocket.accept()
        logger.info(f"聊天WS: {admin_id} @ {server_id} 已连接")
        return True

    async def disconnect(self, admin_id: str, server_id: str):
        """断开连接"""
        key = (admin_id, server_id)
        async with self._lock:
            if key in self.active_connections:
                del self.active_connections[key]
        logger.info(f"聊天WS: {admin_id} @ {server_id} 已断开")

    async def send_message(self, admin_id: str, server_id: str, message: dict) -> bool:
        """向指定客户端发送消息"""
        key = (admin_id, server_id)
        async with self._lock:
            ws = self.active_connections.get(key)

        if ws is None:
            return False

        try:
            await ws.send_text(json.dumps(message, ensure_ascii=False))
            return True
        except Exception as e:
            logger.error(f"聊天WS发送失败 {admin_id}@{server_id}: {e}")
            return False

    async def is_connected(self, admin_id: str, server_id: str) -> bool:
        """检查连接是否存活"""
        key = (admin_id, server_id)
        async with self._lock:
            return key in self.active_connections


chat_manager = ChatConnectionManager()
