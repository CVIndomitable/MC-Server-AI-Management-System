"""滑动计数限流：Redis 可用时走 Redis（集群共享），不可用时降级到进程内存字典。

只做计数，不做严格滑动窗口（使用 INCR+EXPIRE 的"固定窗口"近似）——
在安全边界上略宽（最多允许 2x 瞬时突发），但实现简单、性能好、集群下共享。
"""

from collections import defaultdict
from typing import Optional
import time
import logging

logger = logging.getLogger(__name__)

# 进程内存降级存储
_memory_store: dict[str, list[float]] = defaultdict(list)


def _memory_check(key: str, limit: int, window: int) -> bool:
    """返回 True 表示已超限"""
    now = time.time()
    bucket = _memory_store[key]
    # 丢弃过期记录
    _memory_store[key] = [t for t in bucket if now - t < window]
    if len(_memory_store[key]) >= limit:
        return True
    _memory_store[key].append(now)
    return False


async def check_and_increment(key: str, limit: int, window: int) -> bool:
    """检查 key 在 window 秒内的计数是否已达 limit；未达则 +1。
    返回 True 表示已达限额（应拒绝请求）。
    """
    redis_client = _get_redis()
    if redis_client is None:
        return _memory_check(key, limit, window)

    full_key = f"rl:{key}"
    try:
        # 原子 INCR；仅在首次创建时设 TTL（INCR 对已有 key 不重置 TTL）
        count = await redis_client.incr(full_key)
        if count == 1:
            await redis_client.expire(full_key, window)
        if count > limit:
            return True
        return False
    except Exception as e:
        logger.warning(f"Redis rate limit 查询失败，降级到内存: {e}")
        return _memory_check(key, limit, window)


def _get_redis():
    """获取 memory_service 的共享 Redis 连接；未初始化则返回 None"""
    try:
        from app.services.memory import memory_service
        return memory_service._redis
    except Exception:
        return None
