from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Optional
import json
import asyncio
import secrets
from datetime import datetime
from config.settings import settings
from app.models.schemas import StatusReport, CommandResult
import uuid
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.server_status: Dict[str, dict] = {}
        self.pending_commands: Dict[str, asyncio.Future] = {}
        # 客户端 WS 注册表：(admin_id, server_id) → WebSocket
        # 用于把异步事件主动推给对应的前端会话
        self.client_connections: Dict[tuple, WebSocket] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start_cleanup(self):
        """启动僵死连接清理任务"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("WebSocket 僵死连接清理任务已启动")

    async def stop_cleanup(self):
        """停止清理任务"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self):
        """每30秒检查一次僵死连接"""
        while True:
            try:
                await asyncio.sleep(30)
                await self._remove_stale_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"连接清理出错: {e}")

    async def _remove_stale_connections(self):
        """移除超过60秒无状态上报的连接"""
        now = datetime.now()
        stale = []
        async with self._lock:
            for server_id, status in self.server_status.items():
                if server_id in self.active_connections:
                    last_update = status.get("last_update")
                    if last_update and (now - last_update).total_seconds() > 60:
                        stale.append(server_id)
        for server_id in stale:
            logger.warning(f"服务器 {server_id} 心跳超时，断开连接")
            async with self._lock:
                ws = self.active_connections.get(server_id)
            if ws:
                try:
                    await ws.close(code=1000, reason="Heartbeat timeout")
                except Exception:
                    pass
            await self.disconnect(server_id)

    async def connect(self, websocket: WebSocket, server_id: str, token: str):
        client_ip = websocket.client.host if websocket.client else "unknown"

        # 常量时间比较，防时序攻击
        if not secrets.compare_digest(token or "", settings.mod_auth_token):
            logger.warning(f"WS 鉴权失败: server_id={server_id} ip={client_ip}")
            await websocket.close(code=1008, reason="Invalid token")
            return False

        # 拒绝同一 server_id 的并发连接，防止劫持已在线的模组
        async with self._lock:
            if server_id in self.active_connections:
                existing = self.active_connections[server_id]
                existing_ip = existing.client.host if existing.client else "unknown"
                logger.warning(
                    f"WS 拒绝重复连接: server_id={server_id} 已被 {existing_ip} 占用，新请求来自 {client_ip}"
                )
                await websocket.close(code=1008, reason="server_id already connected")
                return False

        # 服务器注册策略：未知 server_id 是否允许首次连入自动入库
        # 生产配置 mod_allow_new_servers=false 时，需要管理员预先注册才能连入
        from app.core.database import user_db
        try:
            existing = await user_db.get_server(server_id)
        except Exception as e:
            logger.warning(f"查询服务器失败: {e}")
            existing = None

        if existing is None and not settings.mod_allow_new_servers:
            logger.warning(
                f"WS 拒绝未注册 server_id={server_id} (ip={client_ip})；"
                f"需管理员先注册或启用 MOD_ALLOW_NEW_SERVERS"
            )
            await websocket.close(code=1008, reason="server_id not registered")
            return False

        await websocket.accept()

        # 记录（或刷新）服务器状态
        try:
            await user_db.register_server(server_id)
        except Exception as e:
            logger.warning(f"服务器注册失败: {e}")

        async with self._lock:
            self.active_connections[server_id] = websocket
            self.server_status[server_id] = {
                "online": True,
                "last_update": datetime.now(),
                "data": {}
            }
        logger.info(f"Server {server_id} connected from {client_ip} and registered")
        return True

    async def disconnect(self, server_id: str):
        async with self._lock:
            if server_id in self.active_connections:
                del self.active_connections[server_id]
            if server_id in self.server_status:
                self.server_status[server_id]["online"] = False
        logger.info(f"Server {server_id} disconnected")

    async def handle_message(self, server_id: str, message: dict):
        msg_type = message.get("type")

        if msg_type == "status":
            async with self._lock:
                self.server_status[server_id] = {
                    "online": True,
                    "last_update": datetime.now(),
                    "data": message.get("data", {})
                }

        elif msg_type == "result":
            command_id = message.get("command_id")
            if command_id in self.pending_commands:
                future = self.pending_commands.pop(command_id)
                if not future.done():
                    future.set_result(message)

        elif msg_type == "ai_chat_request":
            # 游戏内玩家通过模组发起的 AI 对话
            from app.services.mod_chat_bridge import handle_ai_chat_request
            asyncio.create_task(handle_ai_chat_request(server_id, message))

        elif msg_type == "async_event":
            # 模组侧后台产生的异步事件（目前：Spark profiler 报告）
            from app.services.async_event_bridge import async_event_bridge
            asyncio.create_task(async_event_bridge.handle_async_event(server_id, message))

    async def send_raw(self, server_id: str, message: dict) -> bool:
        """直接向指定服务器发送任意 JSON 消息（不期待响应）"""
        async with self._lock:
            ws = self.active_connections.get(server_id)
        if ws is None:
            logger.warning(f"send_raw: server {server_id} 未连接")
            return False
        try:
            await ws.send_text(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"send_raw 发送失败 server={server_id}: {e}")
            return False

    async def send_command(self, server_id: str, action: str, payload: dict, timeout: int = 30) -> dict:
        async with self._lock:
            if server_id not in self.active_connections:
                return {"success": False, "output": "服务器未连接"}
            websocket = self.active_connections[server_id]

        command_id = f"cmd_{uuid.uuid4().hex[:12]}"
        command = {
            "type": "command",
            "id": command_id,
            "action": action,
            "payload": payload
        }

        future = asyncio.Future()
        self.pending_commands[command_id] = future

        try:
            await websocket.send_text(json.dumps(command))
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self.pending_commands.pop(command_id, None)
            logger.error(f"Command {command_id} timeout for server {server_id}")
            return {"success": False, "output": "指令执行超时"}
        except Exception as e:
            self.pending_commands.pop(command_id, None)
            logger.error(f"Failed to send command to {server_id}: {e}")
            return {"success": False, "output": f"发送指令失败: {str(e)}"}

    async def get_status(self, server_id: str) -> Optional[dict]:
        async with self._lock:
            return self.server_status.get(server_id)

    async def is_online(self, server_id: str) -> bool:
        async with self._lock:
            return server_id in self.active_connections

    # ---- 客户端 WS 通道 ----

    async def register_client(self, websocket: WebSocket, admin_id: str, server_id: str):
        """登记一个前端 WS 订阅；同 key 覆盖旧连接，避免同一用户在一台设备上并发占坑"""
        key = (admin_id, server_id)
        async with self._lock:
            old = self.client_connections.get(key)
            self.client_connections[key] = websocket
        if old is not None and old is not websocket:
            try:
                await old.close(code=1000, reason="Replaced by new client connection")
            except Exception:
                pass
        logger.info(f"客户端 WS 登记: admin={admin_id} server={server_id}")

    async def unregister_client(self, admin_id: str, server_id: str, websocket: WebSocket):
        """仅当当前登记的连接就是传入的这个才移除，防止新连接覆盖旧连接后被误删"""
        key = (admin_id, server_id)
        async with self._lock:
            current = self.client_connections.get(key)
            if current is websocket:
                del self.client_connections[key]
                logger.info(f"客户端 WS 下线: admin={admin_id} server={server_id}")

    async def send_to_client(self, admin_id: str, server_id: str, payload: dict) -> bool:
        async with self._lock:
            ws = self.client_connections.get((admin_id, server_id))
        if ws is None:
            logger.info(f"客户端 WS 未在线，丢弃推送 admin={admin_id} server={server_id}")
            return False
        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
            return True
        except Exception as e:
            logger.warning(f"客户端推送失败 admin={admin_id} server={server_id}: {e}")
            return False

    async def broadcast_to_server_clients(self, server_id: str, payload: dict) -> int:
        """把 payload 广播给所有订阅此 server_id 的前端"""
        async with self._lock:
            targets = [
                (key, ws)
                for key, ws in self.client_connections.items()
                if key[1] == server_id
            ]
        if not targets:
            return 0
        text = json.dumps(payload, ensure_ascii=False)
        sent = 0
        for key, ws in targets:
            try:
                await ws.send_text(text)
                sent += 1
            except Exception as e:
                logger.warning(f"广播到客户端失败 {key}: {e}")
        return sent

manager = ConnectionManager()
