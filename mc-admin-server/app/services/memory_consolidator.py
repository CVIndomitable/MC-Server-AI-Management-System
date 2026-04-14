"""
记忆整理服务：定时扫描超时会话，调用 LLM 自动整理对话中的有价值信息到三级记忆。
"""
import asyncio
import json
import logging
import time
from typing import Optional, Callable

from anthropic import AsyncAnthropic
from config.settings import settings
from app.services.memory import memory_service, MEMORY_TAGS, VALID_TAGS

logger = logging.getLogger(__name__)

client = AsyncAnthropic(
    api_key=settings.anthropic_api_key,
    base_url=settings.anthropic_base_url,
)

# 生成标签说明文本
_TAG_DESCRIPTIONS = "\n".join(
    f"  - `{tag}`: {info['label']}" for tag, info in MEMORY_TAGS.items()
)

CONSOLIDATION_PROMPT = """你是记忆整理助手。请根据以下对话内容，将有价值的信息提取为结构化记忆条目。

## 可用标签（每条记忆分配 1-3 个）
{tag_descriptions}

## 当前记忆条目

### 全局记忆（通用 MC 运维经验，所有服务器通用）
{current_global_memory}

### 管理员记忆（此管理员的习惯和玩家档案）
{current_admin_memory}

### 服务器记忆（当前整合包/服务器独有的信息）
{current_server_memory}

## 本次对话记录
{conversation_history}

## 更新规则

1. 分类标准：
   - 换任何 MC 服务器都成立 → 全局记忆
   - 跟管理员个人习惯或玩家群体有关 → 管理员记忆
   - 只跟当前整合包/服务器有关，换个包没用 → 服务器记忆

2. 每条记忆是一个独立的知识点，内容简洁（1-3句话）
3. 每条记忆分配 1-3 个标签（从上面的可用标签中选择）
4. 只提取有长期价值的信息，忽略一次性操作（如"查下TPS"）
5. 如果新信息与旧记忆矛盾，用新信息替换旧的
6. 删除已过时的信息
7. 如果现有条目有 "pinned": true，不得修改或删除该条目，原样保留
8. 保留现有条目的 id 字段（如有），新条目不需要 id
9. 如果对话中没有任何有长期价值的新信息，返回原有条目不变
10. 每级记忆控制在 3-8 条，相关内容合并

## 字数限制（所有条目 content 拼接后）
- 全局记忆：不超过 1500 字
- 管理员记忆：不超过 1500 字
- 服务器记忆：不超过 1000 字

请以以下 JSON 格式输出（不要输出其他内容）：

{{
  "global_memory": {{
    "entries": [
      {{"id": "保留已有id或留空", "tags": ["tag1", "tag2"], "content": "记忆内容", "pinned": false}}
    ]
  }},
  "admin_memory": {{
    "entries": [...]
  }},
  "server_memory": {{
    "entries": [...]
  }},
  "changes_summary": "本次变更摘要（用于日志记录）"
}}"""


def _format_conversation(history: list) -> str:
    """将对话历史格式化为可读文本"""
    lines = []
    for msg in history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            # tool_use / tool_result blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        text_parts.append(f"[调用工具: {block.get('name')}({json.dumps(block.get('input', {}), ensure_ascii=False)})]")
                    elif block.get("type") == "tool_result":
                        text_parts.append(f"[工具结果: {block.get('content', '')}]")
                else:
                    # Anthropic SDK content block objects
                    block_type = getattr(block, "type", None)
                    if block_type == "text":
                        text_parts.append(getattr(block, "text", ""))
                    elif block_type == "tool_use":
                        text_parts.append(f"[调用工具: {getattr(block, 'name', '')}({json.dumps(getattr(block, 'input', {}), ensure_ascii=False)})]")
            content = "\n".join(text_parts)

        if role == "user":
            lines.append(f"管理员: {content}")
        elif role == "assistant":
            lines.append(f"AI助手: {content}")
    return "\n".join(lines)


def _format_existing_entries(mem_data: dict) -> str:
    """将现有记忆格式化为 LLM 可读的条目列表"""
    if not mem_data:
        return "（暂无）"
    entries = mem_data.get("entries")
    if entries:
        lines = []
        for e in entries:
            tags_str = ", ".join(e.get("tags", []))
            pinned = " [置顶]" if e.get("pinned") else ""
            id_str = e.get("id", "")
            lines.append(f"- [{tags_str}]{pinned}(id:{id_str}) {e['content']}")
        return "\n".join(lines) if lines else "（暂无）"
    # 无 entries，回退到纯文本
    return mem_data.get("content", "") or "（暂无）"


async def consolidate_session(admin_id: str, server_id: str, conversation_history: list):
    """对一个会话执行记忆整理"""
    if not conversation_history:
        logger.info(f"会话 {admin_id}:{server_id} 无对话记录，跳过整理")
        return

    # 读取当前三级记忆（完整结构化数据）
    global_data = await memory_service.get_memory_with_meta("global") or {}
    admin_data = await memory_service.get_memory_with_meta("admin", admin_id) or {}
    server_data = await memory_service.get_memory_with_meta("server", server_id) or {}

    # 提取置顶条目（用于校验 LLM 未篡改）
    pinned_entries = {}
    for key, data in [("global", global_data), ("admin", admin_data), ("server", server_data)]:
        pinned = [e for e in data.get("entries", []) if e.get("pinned")]
        if pinned:
            pinned_entries[key] = pinned

    # 格式化对话历史
    conv_text = _format_conversation(conversation_history)
    if not conv_text.strip():
        logger.info(f"会话 {admin_id}:{server_id} 对话内容为空，跳过整理")
        return

    prompt = CONSOLIDATION_PROMPT.format(
        tag_descriptions=_TAG_DESCRIPTIONS,
        current_global_memory=_format_existing_entries(global_data),
        current_admin_memory=_format_existing_entries(admin_data),
        current_server_memory=_format_existing_entries(server_data),
        conversation_history=conv_text,
    )

    try:
        # 使用 flash 模型整理，节省费用
        response = await client.messages.create(
            model=settings.model_flash,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text += block.text

        # 解析 JSON（LLM 有时会包裹在 ```json ``` 中）
        json_text = response_text.strip()
        if json_text.startswith("```"):
            lines = json_text.split("\n")
            json_text = "\n".join(lines[1:-1])

        result = json.loads(json_text)

        # 验证并保存各级记忆
        changes = []
        for mem_type, mem_key, mem_id in [
            ("global_memory", "global", ""),
            ("admin_memory", "admin", admin_id),
            ("server_memory", "server", server_id),
        ]:
            mem_result = result.get(mem_type, {})

            # 兼容旧格式（纯字符串）和新格式（含 entries 的 dict）
            if isinstance(mem_result, str):
                # 旧格式回退
                new_content = mem_result.strip()
                if not new_content or new_content == "（暂无）":
                    continue
                save_result = await memory_service.set_memory(mem_key, mem_id, new_content)
                if not save_result["success"]:
                    logger.warning(f"记忆超限，尝试压缩: {mem_key}:{mem_id}")
                    new_content = await _compress_memory(mem_key, new_content)
                    if new_content:
                        save_result = await memory_service.set_memory(mem_key, mem_id, new_content)
                        if not save_result["success"]:
                            logger.error(f"压缩后仍超限: {mem_key}:{mem_id}，跳过")
                            continue
                changes.append(mem_key)
                continue

            # 新格式：结构化 entries
            entries = mem_result.get("entries", [])
            if not entries:
                continue

            # 过滤无效标签
            for entry in entries:
                entry["tags"] = [t for t in entry.get("tags", []) if t in VALID_TAGS]

            # 置顶保护：确保 LLM 未篡改置顶条目
            if mem_key in pinned_entries:
                original_pinned = pinned_entries[mem_key]
                # 移除 LLM 返回中的置顶条目，用原始版本替代
                entries = [e for e in entries if not e.get("pinned")]
                entries = original_pinned + entries

            save_result = await memory_service.set_structured_memory(mem_key, mem_id, entries)
            if not save_result["success"]:
                logger.warning(f"结构化记忆超限，尝试压缩: {mem_key}:{mem_id}")
                # 拼接为文本后压缩
                content = "\n\n".join(e["content"] for e in entries)
                compressed = await _compress_memory(mem_key, content)
                if compressed:
                    save_result = await memory_service.set_memory(mem_key, mem_id, compressed)
                    if not save_result["success"]:
                        logger.error(f"压缩后仍超限: {mem_key}:{mem_id}，跳过")
                        continue
            changes.append(mem_key)

        summary = result.get("changes_summary", "无变更摘要")
        logger.info(f"记忆整理完成 [{admin_id}:{server_id}]: {summary} (更新了: {','.join(changes) if changes else '无变更'})")

    except json.JSONDecodeError as e:
        logger.error(f"记忆整理 JSON 解析失败: {e}\n原始响应: {response_text[:500]}")
    except Exception as e:
        logger.error(f"记忆整理失败 [{admin_id}:{server_id}]: {e}")


async def _compress_memory(mem_type: str, content: str) -> Optional[str]:
    """调用 LLM 压缩超限的记忆"""
    from app.services.memory import GLOBAL_MEMORY_LIMIT, ADMIN_MEMORY_LIMIT, SERVER_MEMORY_LIMIT
    limits = {"global": GLOBAL_MEMORY_LIMIT, "admin": ADMIN_MEMORY_LIMIT, "server": SERVER_MEMORY_LIMIT}
    limit = limits.get(mem_type, 1000)

    try:
        response = await client.messages.create(
            model=settings.model_flash,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": f"以下记忆内容超出了{limit}字的限制（当前{len(content)}字）。"
                           f"请压缩到{limit}字以内，保留最重要的信息，删除次要内容。"
                           f"如果有 '## 置顶（勿删）' 区块，该区域不得修改。"
                           f"直接输出压缩后的 Markdown 文本，不要输出其他内容。\n\n{content}",
            }],
        )
        result_text = ""
        for block in response.content:
            if block.type == "text":
                result_text += block.text
        result_text = result_text.strip()
        if len(result_text) <= limit:
            return result_text
        return None
    except Exception as e:
        logger.error(f"记忆压缩失败: {e}")
        return None


class MemoryConsolidator:
    """后台定时任务：扫描超时会话并整理记忆"""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._get_conversation: Optional[Callable] = None

    async def start(self, get_conversation_fn):
        """启动后台定时任务

        Args:
            get_conversation_fn: 获取对话历史的回调函数 (admin_id, server_id) -> list
        """
        self._running = True
        self._get_conversation = get_conversation_fn
        self._task = asyncio.create_task(self._loop())
        logger.info("记忆整理后台任务已启动")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("记忆整理后台任务已停止")

    async def _loop(self):
        """每分钟扫描一次超时会话"""
        while self._running:
            try:
                await self._scan_and_consolidate()
            except Exception as e:
                logger.error(f"记忆整理扫描出错: {e}")
            await asyncio.sleep(60)  # 每分钟检查一次

    async def _scan_and_consolidate(self):
        """扫描超时会话并触发整理"""
        stale_sessions = await memory_service.get_stale_sessions(timeout_seconds=600)
        if not stale_sessions:
            return

        logger.info(f"发现 {len(stale_sessions)} 个超时会话待整理")

        for session in stale_sessions:
            admin_id = session["admin_id"]
            server_id = session["server_id"]
            session_key = session["_key"]

            # 获取对话历史
            conversation = self._get_conversation(admin_id, server_id)
            if conversation:
                await consolidate_session(admin_id, server_id, conversation)

            # 标记为已整理
            await memory_service.mark_session_consolidated(session_key)


memory_consolidator = MemoryConsolidator()
