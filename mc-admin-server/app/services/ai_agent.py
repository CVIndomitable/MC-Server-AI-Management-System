from anthropic import AsyncAnthropic
from config.settings import settings
from typing import List, Dict, Any, Optional
from app.services.memory import memory_service
from app.services.command_cache import command_cache
import json
import re
import logging
import uuid
import copy

logger = logging.getLogger(__name__)

client = AsyncAnthropic(
    api_key=settings.anthropic_api_key,
    base_url=settings.anthropic_base_url,
)

SYSTEM_PROMPT_BASE = """你是一个Minecraft服务器管理助手。你可以通过以下工具管理服务器：

- execute_command: 执行任意MC指令（指令的文本输出会完整返回给你）
- kick_player: 踢出玩家
- op_player: 给予玩家OP权限
- deop_player: 移除玩家OP权限
- get_status: 获取服务器状态
- restart_server: 重启服务器
- broadcast: 发送全服公告

## Spark 性能分析模组

服务器安装了 Spark 性能分析模组，你可以通过 execute_command 调用以下命令进行深度性能诊断：

**性能指标**
- `/spark tps` — 查看TPS和CPU使用率（比 get_status 更详细）
- `/spark ping` 或 `/spark ping --player 玩家名` — 查看玩家延迟

**健康报告**
- `/spark health` — 生成完整的服务器健康报告（TPS、CPU、内存、磁盘）
- `/spark health --memory` — 附带JVM内存详情

**性能剖析**
- `/spark profiler start` — 开始CPU性能剖析
- `/spark profiler start --timeout 30` — 剖析30秒后自动停止
- `/spark profiler start --only-ticks-over 50` — 只记录超过50ms的卡顿tick
- `/spark profiler stop` — 停止剖析并生成报告链接
- `/spark profiler info` — 查看当前剖析状态

**Tick监控**
- `/spark tickmonitor` — 开启/关闭tick耗时监控
- `/spark tickmonitor --threshold 150` — 只报告超过正常150%的tick

**内存分析**
- `/spark gc` — 查看GC历史记录
- `/spark gcmonitor` — 开启/关闭GC实时监控
- `/spark heapsummary` — 生成堆内存摘要（排查内存泄漏）

**使用场景指引**：
- 用户问"卡不卡"、"服务器性能怎么样" → 先看状态数据中的 spark 字段（已自动上报），必要时用 `/spark health`
- 用户说"服务器卡顿"、"TPS低" → 按以下卡顿诊断流程处理
- 用户问"内存占用高" → 用 `/spark heapsummary` 分析内存分布
- 用户问"某玩家延迟高" → 用 `/spark ping --player 玩家名`
- 注意：profiler start 是异步操作，start后需等待再 stop 或等超时，stop 后才有结果

**卡顿诊断流程**（当用户报告卡顿/lag spike时）：
1. 先查看状态数据中的 spark.tps 和 spark.mspt，初步判断严重程度
2. 开启tick监控：`/spark tickmonitor` 或 `/spark tickmonitor --threshold-tick 50`，让它运行一段时间来捕捉卡顿发生的模式
3. 使用针对性profiler：`/spark profiler start --only-ticks-over 100`，这会只采样超过100ms的卡顿tick，过滤掉正常tick的干扰（阈值根据实际情况调整，一般50-150ms）
4. 等待足够时间后停止：`/spark profiler stop`，会生成分析报告链接
5. 常见卡顿原因：WorldEdit大操作、区块生成、实体过多、红石机器、插件/模组bug

**状态数据中的 Spark 字段说明**：
服务器每次上报状态时会自动包含 spark 对象（如果安装了Spark），包含：
- spark.tps: {10s, 1m, 5m, 15m} — 多窗口TPS，比基础TPS更准确
- spark.mspt: {10s: {mean, p95}, 1m: {mean, p50, p95, max}} — 每tick毫秒数及百分位
- spark.cpu: {process_10s, process_1m, system_10s, system_1m} — CPU使用率百分比
- spark.gc: {收集器名: {total_count, avg_time_ms, avg_frequency_ms}} — GC统计

请根据用户的自然语言请求，选择合适的工具执行操作。回复时用中文，简洁明了。"""

QUERY_ONLY_PROMPT_BASE = """你是一个Minecraft服务器管理助手，当前处于【仅查询模式】。

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
TECH_WORDS = re.compile(r"TPS|tps|内存|日志|报错|错误|延迟|卡顿|spark|Spark|性能剖析|GC|堆内存")

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
        self.conversation_history: Dict[tuple, List[Dict]] = {}
        self.max_history_length = 50
        self.max_conversations = 200
        self._access_order: Dict[tuple, float] = {}  # LRU跟踪

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

    def _touch_conversation(self, hkey: tuple):
        """更新会话访问时间，必要时淘汰最久未使用的会话"""
        import time as _time
        self._access_order[hkey] = _time.time()
        if len(self.conversation_history) > self.max_conversations:
            oldest = min(self._access_order, key=self._access_order.get)
            self.conversation_history.pop(oldest, None)
            self._access_order.pop(oldest, None)
            logger.info(f"会话淘汰(LRU): {oldest}")

    async def process_message(self, user_message: str, server_id: str, current_status: dict = None, query_only: bool = False, model_tier: Optional[str] = None, admin_id: str = "admin") -> Dict[str, Any]:
        hkey = (admin_id, server_id)
        if hkey not in self.conversation_history:
            self.conversation_history[hkey] = []
        self._touch_conversation(hkey)

        # 使用结构化消息分离用户输入和系统状态，防止Prompt Injection
        if current_status:
            user_msg = {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message},
                    {"type": "text", "text": f"[系统附加·当前服务器状态]{json.dumps(current_status, ensure_ascii=False)}"},
                ]
            }
        else:
            user_msg = {"role": "user", "content": user_message}

        self.conversation_history[hkey].append(user_msg)
        self._trim_history(hkey)

        # ---- 命令缓存：相同消息直接复用上次的工具调用 ----
        if not query_only:
            try:
                cached = await command_cache.get(user_message, server_id, user_id=admin_id)
            except Exception as e:
                logger.warning(f"缓存查询失败，跳过: {e}")
                cached = None
            if cached:
                logger.info(f"[{server_id}] 缓存命中，跳过大模型调用: '{user_message[:40]}'")
                result = {
                    "text": cached["text"],
                    "tool_calls": [],
                    "model_used": cached.get("model_used", "cache"),
                    "cache_hit": True,
                }
                content_blocks = []
                if cached["text"]:
                    content_blocks.append({"type": "text", "text": cached["text"]})
                for tc in cached["tool_calls"]:
                    new_id = f"cache_{uuid.uuid4().hex[:12]}"
                    result["tool_calls"].append({
                        "id": new_id,
                        "name": tc["name"],
                        "input": copy.deepcopy(tc["input"]),
                    })
                    content_blocks.append({
                        "type": "tool_use",
                        "id": new_id,
                        "name": tc["name"],
                        "input": copy.deepcopy(tc["input"]),
                    })
                self.conversation_history[hkey].append({
                    "role": "assistant",
                    "content": content_blocks,
                })
                return result

        # ---- 正常调用大模型 ----
        model = self._resolve_model(user_message, query_only, model_tier)
        logger.info(f"[{server_id}] 模型路由: {model} (tier={model_tier}, query_only={query_only}, msg_len={len(user_message)})")

        base_prompt = QUERY_ONLY_PROMPT_BASE if query_only else SYSTEM_PROMPT_BASE
        system_prompt = await self._build_system_prompt(base_prompt, admin_id, server_id, user_message=user_message)

        create_params = {
            "model": model,
            "max_tokens": 2048,
            "system": system_prompt,
            "messages": self.conversation_history[hkey],
        }
        if not query_only:
            create_params["tools"] = TOOLS

        response = await client.messages.create(**create_params)

        assistant_msg = {"role": "assistant", "content": response.content}
        self.conversation_history[hkey].append(assistant_msg)

        result = {
            "text": "",
            "tool_calls": [],
            "model_used": model,
        }

        allowed_tools = {t["name"] for t in TOOLS}
        for block in response.content:
            if block.type == "text":
                result["text"] += block.text
            elif block.type == "tool_use":
                if block.name not in allowed_tools:
                    logger.warning(f"AI返回了未知工具调用: {block.name}，已忽略")
                    continue
                result["tool_calls"].append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })

        # 缓存包含工具调用的结果到 Redis
        if not query_only:
            try:
                await command_cache.put(user_message, server_id, result, user_id=admin_id)
            except Exception as e:
                logger.warning(f"缓存写入失败: {e}")

        return result

    def add_tool_result(self, admin_id: str, server_id: str, tool_use_id: str, result: str):
        hkey = (admin_id, server_id)
        if hkey not in self.conversation_history or not self.conversation_history[hkey]:
            return

        # 限制工具结果长度，防止超大结果污染对话
        max_result_len = 8192
        if len(result) > max_result_len:
            result = result[:max_result_len] + "\n...(结果已截断)"

        last_msg = self.conversation_history[hkey][-1]
        if last_msg["role"] != "user":
            self.conversation_history[hkey].append({
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

    async def _build_system_prompt(self, base_prompt: str, admin_id: str, server_id: str, user_message: str = "") -> str:
        """拼接基础 prompt + 三级记忆（根据用户问题智能过滤）"""
        try:
            memory_prompt = await memory_service.build_memory_prompt(admin_id, server_id, user_message=user_message)
            if memory_prompt.replace("（暂无）", "").strip():
                return base_prompt + "\n\n以下是你的记忆，请基于这些记忆协助管理员：" + memory_prompt
        except Exception as e:
            logger.warning(f"记忆加载失败，使用基础 prompt: {e}")
        return base_prompt

    def _trim_history(self, hkey):
        if len(self.conversation_history[hkey]) > self.max_history_length:
            self.conversation_history[hkey] = self.conversation_history[hkey][-self.max_history_length:]

ai_agent = AIAgent()
