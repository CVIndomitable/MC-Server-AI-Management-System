"""
Spark profiler 报告分析器。

流程：
1. 抓取 spark.lucko.me URL 内容（HTML），提取可读文本。
2. 送给 Claude，启用 extended thinking（budget_tokens），收集 thinking + text 块。
3. 如果网关不支持 thinking 参数，退回普通调用，thinking 留空。
4. 失败用 provider_pool 的 failover 自动换 provider。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

import httpx
from anthropic import BadRequestError

from app.services.ai_client import provider_pool, NoProviderAvailableError
from config.settings import settings

logger = logging.getLogger(__name__)

# 抓取设置
_FETCH_TIMEOUT = 15.0
_FETCH_MAX_BYTES = 512 * 1024       # 最多读 512KB
_PROMPT_MAX_CHARS = 24_000          # 喂给模型的报告文本上限

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

SYSTEM_PROMPT = """你是 Minecraft 服务器性能诊断专家，精通 Spark profiler 报告的解读。

收到的是一份 spark 性能剖析报告（可能是 HTML 抓取后的文本摘要）。
请基于报告内容产出一份**结构化中文分析**，要求：

1. **总体判断**：服务器当前健康度（正常 / 轻度卡顿 / 严重卡顿），引用关键指标（TPS、MSPT、CPU、GC）。
2. **瓶颈定位**：从调用栈/热点方法里找出占用最高的 N 条路径，说明它们属于什么子系统（区块生成、实体tick、红石、mod/插件等）。
3. **可能原因**：结合 MC 服务器常识给出合理推断，列出 2-4 个最可能的元凶。
4. **建议操作**：具体可执行的优化建议，优先级从高到低。必要时给出 spark 进一步诊断指令。
5. **需要追问的信息**：如果报告信息不足以下定论，明确列出还需要哪些数据。

如果报告内容过少或抓取失败，诚实说明，并引导用户提供更多上下文。"""


def _strip_html(text: str) -> str:
    """抽出 HTML 可读正文。spark 页面本身是 SPA，但 meta/title 里有摘要信息。"""
    if not text:
        return ""
    # 去掉 <script>/<style> 全块
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


async def fetch_profile_content(url: str) -> tuple[str, Optional[str]]:
    """抓取 spark 报告页面。返回 (文本内容, 错误原因)。

    Spark 报告页是 JS 动态渲染的 SPA，直接 GET 只能拿到空壳。
    这里检测到 spark.lucko.me URL 时，自动改用其 JSON data API
    (https://spark.lucko.me/data/{id}) 获取原始性能数据。
    """
    if not url:
        return "", "URL 为空"
    try:
        # 检测 spark URL，改用 JSON data API
        spark_match = re.match(r"https?://spark\.lucko\.me/([A-Za-z0-9_\-]+)$", url.strip())
        fetch_url = f"https://spark.lucko.me/data/{spark_match.group(1)}" if spark_match else url

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=_FETCH_TIMEOUT,
            headers={
                "User-Agent": "mc-admin-server spark-analyzer/1.0",
                "Accept": "application/json,text/html,*/*",
            },
        ) as client:
            resp = await client.get(fetch_url)
            if resp.status_code >= 400:
                return "", f"抓取失败 HTTP {resp.status_code}"
            content = resp.text
            if len(content.encode("utf-8", "ignore")) > _FETCH_MAX_BYTES:
                content = content[:_FETCH_MAX_BYTES]
            content_type = resp.headers.get("content-type", "").lower()
            if "html" in content_type:
                content = _strip_html(content)
            elif "json" in content_type and spark_match:
                # JSON 数据需要格式化后给 AI 解读
                try:
                    data = json.loads(content)
                    content = json.dumps(data, ensure_ascii=False, indent=2)
                except json.JSONDecodeError:
                    pass  # 保持原文
            return content, None
    except httpx.TimeoutException:
        return "", "抓取超时"
    except Exception as e:
        return "", f"抓取异常: {e}"


def _extract_blocks(response) -> tuple[str, str]:
    """从 Anthropic 响应里分离 text 和 thinking 块。"""
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(getattr(block, "text", "") or "")
        elif btype == "thinking":
            thinking_parts.append(getattr(block, "thinking", "") or "")
        elif btype == "redacted_thinking":
            thinking_parts.append("[thinking blocks redacted by provider]")
    return "".join(text_parts).strip(), "\n".join(thinking_parts).strip()


def _build_user_content(url: str, report_text: str, fetch_error: Optional[str]) -> str:
    header = f"Spark 报告链接：{url}\n"
    if fetch_error:
        return (
            header
            + f"\n⚠️ 后端抓取失败：{fetch_error}\n"
            "请根据链接所指向的一般 spark profiler 报告类型，"
            "给出诊断方向的建议（没有具体数字时请明说）。"
        )
    if not report_text:
        return header + "\n（抓取到的内容为空）"
    clipped = report_text[:_PROMPT_MAX_CHARS]
    truncated_note = ""
    if len(report_text) > _PROMPT_MAX_CHARS:
        truncated_note = f"\n\n[内容已截断，原始 {len(report_text)} 字符]"
    return header + "\n报告文本摘要（已剥 HTML）：\n---\n" + clipped + truncated_note + "\n---"


async def analyze_profile(
    url: str,
    server_context: Optional[dict] = None,
    thinking_budget: int = 5000,
    max_tokens: int = 3500,
) -> dict:
    """分析一份 spark 报告。

    返回 {analysis, thinking, model, provider, degraded, fetch_error}。
    抛 NoProviderAvailableError / BadRequestError 由上层捕获。
    """
    report_text, fetch_error = await fetch_profile_content(url)
    user_content = _build_user_content(url, report_text, fetch_error)

    context_prefix = ""
    if server_context:
        tps = server_context.get("tps")
        mspt = server_context.get("mspt")
        players = server_context.get("player_count")
        if any(v is not None for v in (tps, mspt, players)):
            context_prefix = (
                f"\n\n[当前服务器状态参考] TPS={tps} MSPT={mspt} 在线玩家={players}"
            )

    messages = [{"role": "user", "content": user_content + context_prefix}]

    # thinking 参数：thinking 开启时需要 max_tokens > budget_tokens
    effective_max_tokens = max(max_tokens, thinking_budget + 1024)
    create_params = {
        "model": settings.model_pro,
        "max_tokens": effective_max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": messages,
        "thinking": {"type": "enabled", "budget_tokens": thinking_budget},
    }

    try:
        response, used_provider, degraded = await provider_pool.call_with_failover(
            **create_params
        )
    except BadRequestError as e:
        # 网关可能不支持 thinking 参数，退回普通调用
        msg = str(e).lower()
        if "thinking" in msg or "budget_tokens" in msg or "temperature" in msg:
            logger.warning(f"thinking 参数被拒绝，退回普通调用: {e}")
            create_params.pop("thinking", None)
            create_params["max_tokens"] = max_tokens
            response, used_provider, degraded = await provider_pool.call_with_failover(
                **create_params
            )
        else:
            raise

    analysis_text, thinking_text = _extract_blocks(response)

    return {
        "analysis": analysis_text,
        "thinking": thinking_text,
        "model": create_params["model"],
        "provider": used_provider.get("name") if used_provider else None,
        "degraded": degraded,
        "fetch_error": fetch_error,
        "profile_raw": report_text[:_PROMPT_MAX_CHARS] if report_text else None,
    }
