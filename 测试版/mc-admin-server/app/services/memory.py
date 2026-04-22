import redis.asyncio as redis
import json
import time
import uuid
import logging
from typing import Optional, Dict, List, Set
from config.settings import settings

logger = logging.getLogger(__name__)

# 字数上限
GLOBAL_MEMORY_LIMIT = 1500
ADMIN_MEMORY_LIMIT = 1500
SERVER_MEMORY_LIMIT = 1000

# 备份保留数量
MAX_BACKUP_VERSIONS = 10

# ============ 记忆标签体系 ============

MEMORY_TAGS = {
    "performance": {
        "label": "性能优化",
        "keywords": [
            "tps", "mspt", "卡顿", "延迟", "lag", "掉帧", "性能",
            "优化", "内存", "cpu", "gc", "垃圾回收", "tick",
            "区块", "chunk", "预生成", "卡服",
        ],
    },
    "player_mgmt": {
        "label": "玩家管理",
        "keywords": [
            "玩家", "player", "ban", "封禁", "踢出", "kick", "op",
            "权限", "白名单", "whitelist", "破坏",
            "熊孩子", "举报", "作弊", "外挂", "hack", "黑名单",
        ],
    },
    "mods_plugins": {
        "label": "模组/插件",
        "keywords": [
            "mod", "模组", "插件", "plugin", "forge", "fabric",
            "neoforge", "bukkit", "spigot", "paper", "配置",
            "config", "yml", "toml", "整合包", "modpack",
            "安装", "更新", "版本", "兼容", "冲突",
        ],
    },
    "world_mgmt": {
        "label": "世界管理",
        "keywords": [
            "世界", "world", "地图", "存档", "备份", "回档",
            "种子", "seed", "边界", "border", "重置", "生成",
            "维度", "dimension", "地狱", "末地", "nether", "end",
        ],
    },
    "server_ops": {
        "label": "服务器运维",
        "keywords": [
            "重启", "restart", "启动", "start", "关服", "stop",
            "崩溃", "crash", "日志", "log", "报错", "error",
            "部署", "docker", "端口", "网络", "连接", "超时",
            "java", "jvm", "参数",
        ],
    },
    "gameplay": {
        "label": "游戏玩法",
        "keywords": [
            "红石", "redstone", "指令", "command", "命令方块",
            "数据包", "datapack", "合成", "recipe", "附魔",
            "经验", "刷怪", "farm", "交易", "村民",
            "难度", "游戏规则", "gamerule",
        ],
    },
    "economy_social": {
        "label": "经济/社交",
        "keywords": [
            "经济", "economy", "商店", "shop", "金币", "货币",
            "交易", "领地", "claim", "组队", "公会",
            "聊天", "chat", "公告", "broadcast",
        ],
    },
}

VALID_TAGS = set(MEMORY_TAGS.keys())


def classify_question(message: str) -> Set[str]:
    """根据用户消息内容匹配记忆标签（纯关键词子串匹配，零 API 调用）"""
    message_lower = message.lower()
    matched = set()
    for tag, info in MEMORY_TAGS.items():
        for kw in info["keywords"]:
            if kw in message_lower:
                matched.add(tag)
                break
    return matched


class MemoryService:
    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def init(self):
        """初始化 Redis 连接"""
        self._redis = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
        )
        # 验证连接
        await self._redis.ping()
        logger.info("记忆服务 Redis 连接成功")

    async def close(self):
        if self._redis:
            await self._redis.close()

    # ============ Key 生成 ============

    def _key(self, mem_type: str, mem_id: str = "") -> str:
        """生成 Redis key"""
        if mem_type == "global":
            return "memory:global"
        return f"memory:{mem_type}:{mem_id}"

    def _backup_key(self, mem_type: str, mem_id: str = "") -> str:
        if mem_type == "global":
            return "memory:backup:global"
        return f"memory:backup:{mem_type}:{mem_id}"

    def _char_limit(self, mem_type: str) -> int:
        limits = {
            "global": GLOBAL_MEMORY_LIMIT,
            "admin": ADMIN_MEMORY_LIMIT,
            "server": SERVER_MEMORY_LIMIT,
        }
        return limits.get(mem_type, 1000)

    # ============ 读取 ============

    async def get_memory(self, mem_type: str, mem_id: str = "") -> Optional[str]:
        """读取记忆内容"""
        data = await self._redis.get(self._key(mem_type, mem_id))
        if data:
            obj = json.loads(data)
            return obj["content"]
        return None

    async def get_memory_with_meta(self, mem_type: str, mem_id: str = "") -> Optional[dict]:
        """读取记忆内容及元数据"""
        data = await self._redis.get(self._key(mem_type, mem_id))
        if data:
            return json.loads(data)
        return None

    # ============ 写入 ============

    async def set_memory(self, mem_type: str, mem_id: str, content: str) -> dict:
        """写入记忆，自动备份旧版本"""
        char_limit = self._char_limit(mem_type)
        if len(content) > char_limit:
            return {
                "success": False,
                "error": f"内容超出字数限制（{len(content)}/{char_limit}字）",
            }

        key = self._key(mem_type, mem_id)

        # 备份旧版本
        old_data = await self._redis.get(key)
        if old_data:
            await self._add_backup(mem_type, mem_id, json.loads(old_data))

        # 写入新版本
        new_data = {
            "content": content,
            "updated_at": time.time(),
        }
        await self._redis.set(key, json.dumps(new_data, ensure_ascii=False))

        logger.info(f"记忆已更新: {key} ({len(content)}字)")
        return {"success": True}

    # ============ 备份与回滚 ============

    async def _add_backup(self, mem_type: str, mem_id: str, old_data: dict):
        """将旧版本加入备份列表（LIFO，最多保留 MAX_BACKUP_VERSIONS 个）"""
        backup_key = self._backup_key(mem_type, mem_id)
        old_data["backup_time"] = time.time()
        await self._redis.lpush(backup_key, json.dumps(old_data, ensure_ascii=False))
        # 裁剪只保留最近 N 个
        await self._redis.ltrim(backup_key, 0, MAX_BACKUP_VERSIONS - 1)

    async def list_backups(self, mem_type: str, mem_id: str = "") -> List[dict]:
        """列出备份版本"""
        backup_key = self._backup_key(mem_type, mem_id)
        raw_list = await self._redis.lrange(backup_key, 0, -1)
        result = []
        for i, raw in enumerate(raw_list):
            obj = json.loads(raw)
            result.append({
                "version": i,
                "timestamp": obj.get("backup_time", obj.get("updated_at", 0)),
                "content_preview": obj["content"][:100],
            })
        return result

    async def rollback(self, mem_type: str, mem_id: str, version: int) -> dict:
        """回滚到指定备份版本"""
        backup_key = self._backup_key(mem_type, mem_id)
        raw = await self._redis.lindex(backup_key, version)
        if not raw:
            return {"success": False, "error": f"备份版本 {version} 不存在"}

        obj = json.loads(raw)
        content = obj["content"]

        # 当前版本先备份，再用旧版本覆盖
        result = await self.set_memory(mem_type, mem_id, content)
        if result["success"]:
            logger.info(f"记忆已回滚: {mem_type}:{mem_id} → 版本 {version}")
        return result

    # ============ 结构化记忆（条目化存储） ============

    async def _get_structured_memory(self, mem_type: str, mem_id: str = "") -> dict:
        """读取含 entries 的完整结构化记忆数据"""
        data = await self._redis.get(self._key(mem_type, mem_id))
        if data:
            return json.loads(data)
        return {}

    def _filter_entries(self, memory_data: dict, matched_tags: Set[str]) -> str:
        """按标签过滤记忆条目，始终包含置顶条目"""
        entries = memory_data.get("entries")
        if not entries:
            # 无结构化条目，回退到全量 content
            return memory_data.get("content", "") or "（暂无）"

        selected = []
        for entry in entries:
            if entry.get("pinned"):
                selected.append(entry["content"])
            elif set(entry.get("tags", [])) & matched_tags:
                selected.append(entry["content"])

        return "\n\n".join(selected) if selected else "（暂无）"

    async def set_structured_memory(self, mem_type: str, mem_id: str,
                                     entries: List[dict]) -> dict:
        """保存结构化记忆条目，自动拼接 content 字段"""
        # 为没有 id 的条目生成 id
        for entry in entries:
            if not entry.get("id"):
                entry["id"] = f"e_{uuid.uuid4().hex[:8]}"
            # 确保 tags 都是合法的
            entry["tags"] = [t for t in entry.get("tags", []) if t in VALID_TAGS]
            if "updated_at" not in entry:
                entry["updated_at"] = time.time()

        # 拼接 content（用于字数限制检查和向后兼容）
        content = "\n\n".join(e["content"] for e in entries)
        char_limit = self._char_limit(mem_type)
        if len(content) > char_limit:
            return {
                "success": False,
                "error": f"内容超出字数限制（{len(content)}/{char_limit}字）",
            }

        key = self._key(mem_type, mem_id)

        # 备份旧版本
        old_data = await self._redis.get(key)
        if old_data:
            await self._add_backup(mem_type, mem_id, json.loads(old_data))

        new_data = {
            "content": content,
            "entries": entries,
            "updated_at": time.time(),
        }
        await self._redis.set(key, json.dumps(new_data, ensure_ascii=False))

        logger.info(f"结构化记忆已更新: {key} ({len(entries)}条, {len(content)}字)")
        return {"success": True}

    # ============ 三级记忆拼接（注入 system prompt） ============

    async def build_memory_prompt(self, admin_id: str, server_id: str,
                                   user_message: str = "") -> str:
        """拼接三级记忆，根据用户问题智能过滤相关条目"""
        global_data = await self._get_structured_memory("global")
        admin_data = await self._get_structured_memory("admin", admin_id)
        server_data = await self._get_structured_memory("server", server_id)

        # 分类用户问题
        matched_tags = classify_question(user_message) if user_message else set()

        # 有匹配标签且至少一级记忆有 entries → 智能过滤
        has_entries = any(
            d.get("entries") for d in [global_data, admin_data, server_data]
        )
        if matched_tags and has_entries:
            global_mem = self._filter_entries(global_data, matched_tags)
            admin_mem = self._filter_entries(admin_data, matched_tags)
            server_mem = self._filter_entries(server_data, matched_tags)
        else:
            # 回退：无匹配或无结构化数据 → 全量注入
            global_mem = global_data.get("content", "") or "（暂无）"
            admin_mem = admin_data.get("content", "") or "（暂无）"
            server_mem = server_data.get("content", "") or "（暂无）"

        return (
            f"\n\n===== 通用运维经验 =====\n{global_mem}"
            f"\n\n===== 管理员档案 =====\n{admin_mem}"
            f"\n\n===== 当前服务器 =====\n{server_mem}"
        )

    # ============ 会话活跃时间追踪 ============

    async def update_session_active(self, admin_id: str, server_id: str):
        """记录会话最后活跃时间"""
        session_key = f"session:active:{admin_id}:{server_id}"
        data = {
            "admin_id": admin_id,
            "server_id": server_id,
            "last_active": time.time(),
            "consolidated": False,
        }
        await self._redis.set(session_key, json.dumps(data))
        # 加入活跃会话集合，方便扫描
        await self._redis.sadd("session:active_set", session_key)

    async def get_stale_sessions(self, timeout_seconds: int = 600) -> List[dict]:
        """获取超时未活跃且未整理的会话"""
        now = time.time()
        stale = []
        keys = await self._redis.smembers("session:active_set")
        for key in keys:
            raw = await self._redis.get(key)
            if not raw:
                await self._redis.srem("session:active_set", key)
                continue
            session = json.loads(raw)
            if session.get("consolidated"):
                continue
            if now - session["last_active"] > timeout_seconds:
                session["_key"] = key
                stale.append(session)
        return stale

    async def mark_session_consolidated(self, session_key: str):
        """标记会话已整理"""
        raw = await self._redis.get(session_key)
        if raw:
            session = json.loads(raw)
            session["consolidated"] = True
            await self._redis.set(session_key, json.dumps(session))


memory_service = MemoryService()
