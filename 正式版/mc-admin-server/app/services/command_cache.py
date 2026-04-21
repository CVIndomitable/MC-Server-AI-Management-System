"""
命令缓存服务 — Redis 持久化 + LFU 淘汰

相同的用户消息命中缓存后跳过大模型调用，直接复用工具调用结果。
使用 Redis Sorted Set 按调用次数排序，淘汰时从最少使用的开始删。
"""

import redis.asyncio as redis
import json
import time
import hashlib
import logging
from typing import Optional, Dict, Any
from config.settings import settings

logger = logging.getLogger(__name__)

INDEX_KEY = "cmd_cache:index"  # sorted set: member=hash, score=hit_count


def _data_key(h: str) -> str:
    return f"cmd_cache:data:{h}"


class CommandCacheService:
    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self.ttl = settings.cache_ttl_seconds
        self.max_size = settings.cache_max_size

    async def init(self):
        """复用与 memory_service 相同的 Redis 配置"""
        self._redis = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
        )
        await self._redis.ping()
        size = await self._redis.zcard(INDEX_KEY)
        logger.info(f"命令缓存服务已初始化 (已有 {size} 条, TTL={self.ttl}s, max={self.max_size})")

    async def close(self):
        if self._redis:
            await self._redis.close()

    @staticmethod
    def _hash(message: str, server_id: str, user_id: str = "") -> str:
        """规范化消息文本并生成哈希作为缓存 key（含 server_id + user_id 隔离）"""
        normalized = f"{server_id}:{user_id}:{message.strip().lower()}"
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def get(self, message: str, server_id: str, user_id: str = "") -> Optional[Dict[str, Any]]:
        """查询缓存，命中则增加调用计数并返回结果"""
        h = self._hash(message, server_id, user_id)
        raw = await self._redis.get(_data_key(h))
        if raw is None:
            await self._redis.zrem(INDEX_KEY, h)
            return None
        entry = json.loads(raw)
        # 检查是否过期
        if self.ttl > 0 and time.time() - entry["created_at"] > self.ttl:
            await self._redis.delete(_data_key(h))
            await self._redis.zrem(INDEX_KEY, h)
            return None
        # 命中：增加调用计数
        await self._redis.zincrby(INDEX_KEY, 1, h)
        return entry["result"]

    async def put(self, message: str, server_id: str, result: Dict[str, Any], user_id: str = ""):
        """缓存包含工具调用的 AI 响应"""
        if not result.get("tool_calls"):
            return
        h = self._hash(message, server_id, user_id)
        # 超出上限时淘汰调用最少的条目
        size = await self._redis.zcard(INDEX_KEY)
        if size >= self.max_size:
            await self._evict_lfu()
        entry = {
            "result": result,
            "created_at": time.time(),
            "message": message.strip(),
        }
        await self._redis.set(
            _data_key(h), json.dumps(entry, ensure_ascii=False)
        )
        await self._redis.zadd(INDEX_KEY, {h: 1})
        logger.info(f"命令已缓存: '{message.strip()[:40]}'")

    async def _evict_lfu(self):
        """淘汰调用次数最少的一条缓存"""
        members = await self._redis.zpopmin(INDEX_KEY, 1)
        if members:
            h, score = members[0]
            await self._redis.delete(_data_key(h))
            logger.info(f"缓存淘汰: {h[:16]}... (调用次数={int(score)})")

    async def clear(self):
        """清空全部命令缓存"""
        members = await self._redis.zrange(INDEX_KEY, 0, -1)
        if members:
            pipe = self._redis.pipeline()
            for h in members:
                pipe.delete(_data_key(h))
            pipe.delete(INDEX_KEY)
            await pipe.execute()
        else:
            await self._redis.delete(INDEX_KEY)
        logger.info("命令缓存已全部清空")

    async def stats(self) -> Dict[str, Any]:
        """返回缓存统计信息"""
        size = await self._redis.zcard(INDEX_KEY)
        return {
            "cached_commands": size,
            "max_size": self.max_size,
            "ttl_seconds": self.ttl,
        }


command_cache = CommandCacheService()
