from anthropic import Anthropic
from config.settings import settings
from typing import List, Dict, Any
import json

client = Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """你是一个Minecraft服务器管理助手。你可以通过以下工具管理服务器：

- execute_command: 执行任意MC指令
- kick_player: 踢出玩家
- op_player: 给予玩家OP权限
- deop_player: 移除玩家OP权限
- get_status: 获取服务器状态
- get_logs: 获取最近日志
- restart_server: 重启服务器
- broadcast: 发送全服公告

请根据用户的自然语言请求，选择合适的工具执行操作。回复时用中文，简洁明了。"""

TOOLS = [
    {
        "name": "execute_command",
        "description": "执行任意Minecraft服务器指令",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的MC指令，如 /op Steve"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "kick_player",
        "description": "踢出指定玩家",
        "input_schema": {
            "type": "object",
            "properties": {
                "player": {"type": "string", "description": "玩家名"},
                "reason": {"type": "string", "description": "踢出原因"}
            },
            "required": ["player"]
        }
    },
    {
        "name": "op_player",
        "description": "给予玩家OP权限",
        "input_schema": {
            "type": "object",
            "properties": {
                "player": {"type": "string", "description": "玩家名"}
            },
            "required": ["player"]
        }
    },
    {
        "name": "deop_player",
        "description": "移除玩家OP权限",
        "input_schema": {
            "type": "object",
            "properties": {
                "player": {"type": "string", "description": "玩家名"}
            },
            "required": ["player"]
        }
    },
    {
        "name": "get_status",
        "description": "获取服务器当前状态（TPS、在线玩家、内存等）",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "restart_server",
        "description": "重启Minecraft服务器",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "broadcast",
        "description": "向所有在线玩家发送公告",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "公告内容"}
            },
            "required": ["message"]
        }
    }
]

class AIAgent:
    def __init__(self):
        self.conversation_history: Dict[str, List[Dict]] = {}

    async def process_message(self, user_message: str, server_id: str, current_status: dict = None) -> Dict[str, Any]:
        if server_id not in self.conversation_history:
            self.conversation_history[server_id] = []

        user_msg = {"role": "user", "content": user_message}
        if current_status:
            user_msg["content"] += f"\n\n当前服务器状态：{json.dumps(current_status, ensure_ascii=False)}"

        self.conversation_history[server_id].append(user_msg)

        response = client.messages.create(
            model=settings.model_name,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=self.conversation_history[server_id]
        )

        assistant_msg = {"role": "assistant", "content": response.content}
        self.conversation_history[server_id].append(assistant_msg)

        result = {
            "text": "",
            "tool_calls": []
        }

        for block in response.content:
            if block.type == "text":
                result["text"] += block.text
            elif block.type == "tool_use":
                result["tool_calls"].append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })

        return result

    def add_tool_result(self, server_id: str, tool_use_id: str, result: str):
        if server_id in self.conversation_history:
            self.conversation_history[server_id].append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result
                }]
            })

ai_agent = AIAgent()
