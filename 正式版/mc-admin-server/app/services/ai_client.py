"""
LLM API 供应商池：
- 按 priority 从高到低（数字小=优先）依次尝试
- 可切换错误：网络/超时/5xx/429/认证（换个 key 可能通）
- 非可切换：400（同样的请求换哪个 provider 都错）
- 调用结果返回 (response, used_provider, degraded)，degraded=True 表示使用了非最高优先级的供应商
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from anthropic import (
    AsyncAnthropic,
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    BadRequestError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
    InternalServerError,
    APIError,
)

from app.core.database import user_db

logger = logging.getLogger(__name__)


class NoProviderAvailableError(Exception):
    """没有任何可用的 provider（全部失败或未配置）"""


class ProviderPool:
    def __init__(self):
        self._providers: list[dict] = []  # 按 priority 升序，来自 DB
        self._clients: dict[int, AsyncAnthropic] = {}  # id -> client
        self._lock = asyncio.Lock()
        self._loaded = False

    async def init(self):
        await self.reload()

    async def reload(self):
        """从 DB 重新加载 provider 列表，重建 client 缓存"""
        async with self._lock:
            rows = await user_db.list_providers(only_enabled=True)
            new_clients: dict[int, AsyncAnthropic] = {}
            for row in rows:
                new_clients[row["id"]] = AsyncAnthropic(
                    api_key=row["api_key"],
                    base_url=row["base_url"],
                )
            # 关闭旧 client（如果 anthropic SDK 有 close 方法就调，否则靠 GC）
            for old_client in self._clients.values():
                close_fn = getattr(old_client, "close", None)
                if close_fn is not None:
                    try:
                        result = close_fn()
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        pass
            self._providers = rows
            self._clients = new_clients
            self._loaded = True
            names = [f"{p['name']}(prio={p['priority']})" for p in rows]
            logger.info(f"Provider pool 已加载 {len(rows)} 个供应商: {', '.join(names) or '（空）'}")

    def has_providers(self) -> bool:
        return bool(self._providers)

    def top_provider_name(self) -> Optional[str]:
        return self._providers[0]["name"] if self._providers else None

    async def call_with_failover(self, **create_params) -> tuple[Any, dict, bool]:
        """
        按优先级遍历 provider 调用 messages.create。
        返回 (response, used_provider_dict, degraded)。
        degraded=True 当且仅当成功的 provider 不是列表首位。
        全部失败抛出 NoProviderAvailableError，400 直接抛 BadRequestError。
        """
        if not self._loaded:
            await self.init()
        if not self._providers:
            raise NoProviderAvailableError("未配置任何 LLM API 供应商")

        last_error: Optional[Exception] = None
        requested_model = create_params.get("model")
        for idx, provider in enumerate(self._providers):
            client = self._clients.get(provider["id"])
            if client is None:
                continue
            # 按 provider 的 model_map 替换模型名；无映射则原样透传
            params = dict(create_params)
            model_map = provider.get("model_map") or {}
            if requested_model and requested_model in model_map:
                mapped = model_map[requested_model]
                if mapped and mapped != requested_model:
                    logger.debug(
                        f"Provider '{provider['name']}' 模型映射: {requested_model} → {mapped}"
                    )
                    params["model"] = mapped
            try:
                response = await client.messages.create(**params)
                degraded = idx > 0
                if degraded:
                    logger.warning(
                        f"Provider 降级：已切到 '{provider['name']}'（优先级 {provider['priority']}），"
                        f"前面 {idx} 个供应商不可用"
                    )
                return response, provider, degraded
            except BadRequestError:
                # 400 是请求本身的问题，换 provider 也一样会错
                raise
            except (
                APIConnectionError, APITimeoutError, RateLimitError,
                InternalServerError, AuthenticationError, PermissionDeniedError,
            ) as e:
                last_error = e
                logger.warning(
                    f"Provider '{provider['name']}' 调用失败（{type(e).__name__}），尝试下一个: {e}"
                )
                continue
            except APIStatusError as e:
                # 其他状态码：5xx 切换，4xx 直接抛
                if e.status_code >= 500:
                    last_error = e
                    logger.warning(f"Provider '{provider['name']}' 返回 {e.status_code}，尝试下一个")
                    continue
                raise
            except APIError as e:
                # 未知 APIError，保守切换
                last_error = e
                logger.warning(f"Provider '{provider['name']}' 未知 APIError，尝试下一个: {e}")
                continue

        raise NoProviderAvailableError(
            f"所有 {len(self._providers)} 个供应商均不可用，最后错误: {last_error}"
        )

    async def close(self):
        async with self._lock:
            for client in self._clients.values():
                close_fn = getattr(client, "close", None)
                if close_fn is not None:
                    try:
                        result = close_fn()
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        pass
            self._clients.clear()
            self._providers.clear()
            self._loaded = False


provider_pool = ProviderPool()
