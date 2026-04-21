"""
异步事件桥接：处理模组后台产生、不在原始请求生命周期内的事件
（典型场景：Spark profiler start --timeout N 到期后异步上传报告）。

职责：
- profiler start 发起时登记 (server_id → admin_id) 调用者
- 收到模组 async_event 时定位对应调用者，让 AI 对报告做一轮总结
- 通过客户端 WS 通道把总结主动推给前端
"""
import asyncio
import logging
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

from app.services.ai_agent import ai_agent

logger = logging.getLogger(__name__)

# 调用者登记有效期：profiler 最长支持 --timeout 但保守给 30 分钟
_CALLER_TTL_SEC = 30 * 60
# 每个 server_id 最多保留最近 8 个等待中的 profiler 调用
_MAX_PENDING_PER_SERVER = 8


class _PendingCaller:
    __slots__ = ("admin_id", "started_at", "hint")

    def __init__(self, admin_id: str, hint: str = ""):
        self.admin_id = admin_id
        self.started_at = time.time()
        # hint: 原始命令，如 "/spark profiler start --only-ticks-over 100"
        self.hint = hint


class AsyncEventBridge:
    def __init__(self):
        # server_id → FIFO 队列
        self._callers: Dict[str, Deque[_PendingCaller]] = {}
        self._lock = asyncio.Lock()

    async def register_profiler_caller(self, server_id: str, admin_id: str, hint: str = ""):
        """AI 发起 /spark profiler start 时调用"""
        async with self._lock:
            q = self._callers.setdefault(server_id, deque(maxlen=_MAX_PENDING_PER_SERVER))
            q.append(_PendingCaller(admin_id, hint))
            logger.info(
                f"[async_event] profiler caller 登记: server={server_id} admin={admin_id} hint={hint!r}"
            )

    async def _pop_caller(self, server_id: str) -> Optional[_PendingCaller]:
        async with self._lock:
            q = self._callers.get(server_id)
            if not q:
                return None
            cutoff = time.time() - _CALLER_TTL_SEC
            while q and q[0].started_at < cutoff:
                expired = q.popleft()
                logger.info(
                    f"[async_event] 丢弃过期 profiler 调用者 admin={expired.admin_id} "
                    f"server={server_id} age={time.time() - expired.started_at:.0f}s"
                )
            if not q:
                return None
            return q.popleft()

    async def handle_async_event(self, server_id: str, message: dict):
        event = message.get("event")
        if event == "spark_report":
            await self._handle_spark_report(server_id, message)
        else:
            logger.warning(f"[async_event] 未识别的 event 类型: {event}")

    async def _handle_spark_report(self, server_id: str, message: dict):
        url = (message.get("url") or "").strip()
        raw_text = message.get("text") or ""
        if not url:
            logger.warning(f"[async_event] spark_report 缺 url，忽略: {message}")
            return

        caller = await self._pop_caller(server_id)
        if caller is None:
            # 没找到登记的调用者：可能是玩家在控制台手动启动，或调用者已过期
            # 退化为广播（送给该服务器所有在线客户端）
            logger.info(
                f"[async_event] spark_report 无登记调用者，广播 server={server_id} url={url}"
            )
            summary = f"Spark profiler 采样已完成（来源不明）。\n报告：{url}"
            await _push_to_server(server_id, summary, url=url)
            return

        logger.info(
            f"[async_event] spark_report 定向推送 server={server_id} admin={caller.admin_id} url={url}"
        )
        summary = await _summarize_spark_report(
            admin_id=caller.admin_id,
            server_id=server_id,
            caller_hint=caller.hint,
            url=url,
            raw_text=raw_text,
        )
        await _push_to_client(caller.admin_id, server_id, summary, url=url)


async def _summarize_spark_report(
    *, admin_id: str, server_id: str, caller_hint: str, url: str, raw_text: str
) -> str:
    """把报告作为"系统异步结果"注入该会话，并让 AI 生成一句话总结。
    失败时退回 "已采样完成 + URL" 兜底文本。
    """
    hkey = (admin_id, server_id)
    history = ai_agent.conversation_history.get(hkey)
    if history is None:
        # 会话已不在内存中（服务重启、LRU 淘汰），直接给兜底
        return f"Spark profiler 采样完成（{caller_hint or '之前的剖析任务'}）。\n报告：{url}"

    async_message = (
        f"[系统附加·Spark 异步报告]\n"
        f"先前发起的命令：{caller_hint or '/spark profiler start ...'}\n"
        f"采样已完成，报告链接：{url}\n"
        f"原文片段：{raw_text[:800]}\n"
        f"请基于这份报告给管理员一段中文简述（不超过 3 句，附上链接）。不要调用工具。"
    )
    history.append({"role": "user", "content": async_message})
    ai_agent._trim_history(hkey)

    try:
        summary = await ai_agent.continue_after_tools(
            admin_id=admin_id,
            server_id=server_id,
            user_message=async_message,
            query_only=False,
            model_tier=None,
        )
        text = (summary or {}).get("text", "").strip()
        if text:
            return text
    except Exception as e:
        logger.warning(f"[async_event] AI 总结失败，退回兜底文本: {e}")

    return f"Spark profiler 采样完成。\n报告：{url}"


async def _push_to_client(admin_id: str, server_id: str, text: str, *, url: Optional[str] = None):
    from app.websocket.manager import manager
    payload = {
        "type": "chat_response",
        "server_id": server_id,
        "message": text,
        "origin": "async_event",
    }
    if url:
        payload["url"] = url
    await manager.send_to_client(admin_id, server_id, payload)


async def _push_to_server(server_id: str, text: str, *, url: Optional[str] = None):
    from app.websocket.manager import manager
    payload = {
        "type": "chat_response",
        "server_id": server_id,
        "message": text,
        "origin": "async_event_broadcast",
    }
    if url:
        payload["url"] = url
    await manager.broadcast_to_server_clients(server_id, payload)


async_event_bridge = AsyncEventBridge()
