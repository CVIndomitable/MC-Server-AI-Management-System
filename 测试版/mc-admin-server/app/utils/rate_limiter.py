"""基于Redis的分布式速率限制器"""
import redis.asyncio as redis
from fastapi import HTTPException
import time
import logging
from config.settings import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self):
        self.redis_client: redis.Redis | None = None

    async def init(self):
        """初始化Redis连接"""
        try:
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password if settings.redis_password else None,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            await self.redis_client.ping()
            logger.info("Redis速率限制器初始化成功")
        except Exception as e:
            logger.error(f"Redis连接失败，速率限制将降级到内存模式: {e}")
            self.redis_client = None

    async def close(self):
        """关闭Redis连接"""
        if self.redis_client:
            await self.redis_client.close()

    async def check_rate(self, key: str, limit: int, window: int):
        """
        检查速率限制

        Args:
            key: 限制键（如 "login:ip:1.2.3.4" 或 "chat:user:123"）
            limit: 时间窗口内最大请求数
            window: 时间窗口（秒）

        Raises:
            HTTPException: 超过速率限制时抛出429错误
        """
        if not self.redis_client:
            # 降级到内存模式（仅记录警告，不阻止请求）
            logger.warning(f"Redis不可用，跳过速率限制检查: {key}")
            return

        try:
            # 使用Redis INCR + EXPIRE实现滑动窗口
            current = await self.redis_client.incr(key)
            if current == 1:
                # 首次请求，设置过期时间
                await self.redis_client.expire(key, window)

            if current > limit:
                # 获取剩余时间
                ttl = await self.redis_client.ttl(key)
                raise HTTPException(
                    status_code=429,
                    detail=f"请求过于频繁，请{ttl}秒后再试"
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"速率限制检查失败: {e}")
            # 失败时不阻止请求，避免Redis故障导致服务不可用


# 全局单例
rate_limiter = RateLimiter()
