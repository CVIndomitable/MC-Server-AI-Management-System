"""
Spark profiler 档案服务。

职责：
- 监听 execute_command 的执行结果，识别 /spark profiler start/stop。
- start → 新建一条 running 档案。
- stop → 关联最近的 running 档案，解析输出里的 spark.lucko.me URL 并落库。

只关心 execute_command 这一个工具，其他工具直接放行。
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from app.core.database import user_db

logger = logging.getLogger(__name__)

# spark 上传域名：https://spark.lucko.me/<code> 或 https://spark.lucko.me/<code>?...
_SPARK_URL_RE = re.compile(r"https?://spark\.lucko\.me/[A-Za-z0-9_\-]+")

# 识别 start/stop：允许中间多空格、允许附加参数
_START_RE = re.compile(r"^/?spark\s+profiler\s+start\b", re.IGNORECASE)
_STOP_RE = re.compile(r"^/?spark\s+profiler\s+stop\b", re.IGNORECASE)


def _normalize_cmd(cmd: str) -> str:
    return cmd.strip()


def extract_spark_url(text: str) -> Optional[str]:
    if not text:
        return None
    m = _SPARK_URL_RE.search(text)
    return m.group(0) if m else None


async def capture_execute_command(
    admin_id: str,
    server_id: str,
    command: str,
    result: dict,
) -> None:
    """在 execute_command 执行完成后调用。静默吞异常，绝不影响主流程。"""
    try:
        cmd = _normalize_cmd(command or "")
        if not cmd:
            return
        output = str(result.get("output", "")) if isinstance(result, dict) else ""

        if _START_RE.match(cmd):
            # 无论 start 成功与否都记一条——失败时 status 保持 running 但 stop 时会被忽略
            # 如果已经有 running 档案，先将其标记为 failed（避免串档）
            try:
                stale = await user_db.find_running_spark_profile(server_id)
                if stale:
                    await user_db.set_spark_profile_status(stale["id"], "failed")
                    logger.warning(
                        f"[spark_archive] 旧的 running 档案 #{stale['id']} 被新 start 覆盖，已置为 failed"
                    )
            except Exception as e:
                logger.debug(f"[spark_archive] 清理旧 running 档案失败: {e}")
            profile = await user_db.create_spark_profile(
                admin_id=admin_id, server_id=server_id, start_command=cmd
            )
            logger.info(
                f"[spark_archive] 创建档案 #{profile['id']} server={server_id} cmd={cmd!r}"
            )
            return

        if _STOP_RE.match(cmd):
            running = await user_db.find_running_spark_profile(server_id)
            if not running:
                logger.info(f"[spark_archive] server={server_id} 收到 stop 但无 running 档案，忽略")
                return
            url = extract_spark_url(output)
            updated = await user_db.stop_spark_profile(
                profile_id=running["id"],
                profile_url=url,
                stop_output=output[:4000] if output else None,  # 截断防爆库
            )
            if updated:
                logger.info(
                    f"[spark_archive] 档案 #{running['id']} 已 stop，url={url or '未解析到'}"
                )
    except Exception as e:
        # 故意吞掉：档案功能不能影响主业务
        logger.warning(f"[spark_archive] capture 异常（已忽略）: {e}")
