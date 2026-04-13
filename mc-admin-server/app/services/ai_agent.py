from anthropic import Anthropic
from config.settings import settings
from typing import List, Dict, Any, Optional
import json
import re
import logging

logger = logging.getLogger(__name__)

client = Anthropic(
    api_key=settings.anthropic_api_key,
    base_url=settings.anthropic_base_url,
)

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

QUERY_ONLY_PROMPT = """你是一个Minecraft服务器管理助手，当前处于【仅查询模式】。

在此模式下，你**不能执行任何操作**，只能：
1. 分析用户的需求
2. 告诉用户应该执行什么操作
3. 给出具体的MC指令（如 /op Steve、/kick Player 等）
4. 解释指令的作用和注意事项

请用中文回复，给出清晰的指令建议，但**绝对不要尝试调用任何工具**。
如果用户提供了当前服务器状态，你可以基于状态数据进行分析和建议。"""

# 模型路由关键词
PRO_KEYWORDS = re.compile(
    r"分析原因|诊断|排查|崩溃|全面检查|深度|优化方案|性能调优"
)
# 组合信号：问题词 + 技术词 → pro
QUESTION_WORDS = re.compile(r"为什么|怎么|如何")
TECH_WORDS = re.compile(r"TPS|tps|内存|日志|报错|错误|延迟|卡顿")

STANDARD_KEYWORDS = re.compile(
    r"为什么|怎么办|原因|怎么|如何|什么意思|解释"
    r"|所有|批量|每个|逐个|清理"
)
SMART_MSG_LENGTH_THRESHOLD = 80

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
        self.max_history_length = 50

    def _resolve_model(self, message: str, query_only: bool, model_tier: Optional[str]) -> str:
        """根据消息内容和参数选择合适的模型"""
        # 1. 客户端指定
        if model_tier == "pro":
            return settings.model_pro
        if model_tier == "standard":
            return settings.model_standard
        if model_tier == "flash":
            return settings.model_flash

        # 2. query_only 固定用 flash
        if query_only:
            return settings.model_flash

        # 3. 关键词升级到 pro
        if PRO_KEYWORDS.search(message):
            return settings.model_pro
        # 组合信号：问题词 + 技术词
        if QUESTION_WORDS.search(message) and TECH_WORDS.search(message):
            return settings.model_pro

        # 4. 关键词升级到 standard
        if STANDARD_KEYWORDS.search(message) or len(message) > SMART_MSG_LENGTH_THRESHOLD:
            return settings.model_standard

        # 5. 默认 flash
        return settings.model_flash

    async def process_message(self, user_message: str, server_id: str, current_status: dict = None, query_only: bool = False, model_tier: Optional[str] = None) -> Dict[str, Any]:
        if server_id not in self.conversation_history:
            self.conversation_history[server_id] = []

        user_msg = {"role": "user", "content": user_message}
        if current_status:
            user_msg["content"] += f"\n\n当前服务器状态：{json.dumps(current_status, ensure_ascii=False)}"

        self.conversation_history[server_id].append(user_msg)
        self._trim_history(server_id)

        # 仅查询模式：不传工具，使用建议型系统提示词
        model = self._resolve_model(user_message, query_only, model_tier)
        logger.info(f"[{server_id}] 模型路由: {model} (tier={model_tier}, query_only={query_only}, msg_len={len(user_message)})")

        create_params = {
            "model": model,
            "max_tokens": 2048,
            "system": QUERY_ONLY_PROMPT if query_only else SYSTEM_PROMPT,
            "messages": self.conversation_history[server_id],
        }
        if not query_only:
            create_params["tools"] = TOOLS

        response = client.messages.create(**create_params)

        assistant_msg = {"role": "assistant", "content": response.content}
        self.conversation_history[server_id].append(assistant_msg)

        result = {
            "text": "",
            "tool_calls": [],
            "model_used": model,
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
        if server_id not in self.conversation_history or not self.conversation_history[server_id]:
            return

        last_msg = self.conversation_history[server_id][-1]
        if last_msg["role"] != "user":
            self.conversation_history[server_id].append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result
                }]
            })
        else:
            if not isinstance(last_msg["content"], list):
                last_msg["content"] = [{"type": "text", "text": last_msg["content"]}]
            last_msg["content"].append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result
            })

    def _trim_history(self, server_id: str):
        if len(self.conversation_history[server_id]) > self.max_history_length:
            self.conversation_history[server_id] = self.conversation_history[server_id][-self.max_history_length:]

ai_agent = AIAgent()
