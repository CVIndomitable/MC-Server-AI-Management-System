from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Optional
import json
import asyncio
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
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, server_id: str, token: str):
        if token != settings.mod_auth_token:
            await websocket.close(code=1008, reason="Invalid token")
            return False

        await websocket.accept()
        async with self._lock:
            self.active_connections[server_id] = websocket
            self.server_status[server_id] = {
                "online": True,
                "last_update": datetime.now(),
                "data": {}
            }
        logger.info(f"Server {server_id} connected")
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

manager = ConnectionManager()
