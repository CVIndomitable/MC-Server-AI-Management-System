import aiosqlite
import os
import logging
from datetime import datetime, timezone
from app.core.auth import get_password_hash, verify_password

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "users.db")


class UserDatabase:
    def __init__(self):
        self.db_path = DB_PATH

    async def init(self):
        """初始化数据库，创建所有表"""
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)
        os.chmod(db_dir, 0o700)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS servers (
                    server_id TEXT PRIMARY KEY,
                    name TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_servers (
                    username TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'admin',
                    bound_at TEXT NOT NULL,
                    PRIMARY KEY (username, server_id),
                    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE,
                    FOREIGN KEY (server_id) REFERENCES servers(server_id) ON DELETE CASCADE
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS bind_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    resolved_by TEXT,
                    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE,
                    FOREIGN KEY (server_id) REFERENCES servers(server_id) ON DELETE CASCADE
                )
            """)
            await db.commit()
        logger.info(f"数据库已初始化: {self.db_path}")

    async def ensure_default_admin(self):
        """首次启动时创建默认管理员账号（使用随机密码）"""
        admin = await self.get_user("admin")
        if not admin:
            import secrets
            default_password = secrets.token_urlsafe(16)
            await self.create_user("admin", default_password, role="admin")
            logger.warning(f"已创建默认管理员账号 admin，初始密码: {default_password}")
            logger.warning("请立即登录并修改密码！此密码仅在日志中出现一次。")

    async def create_user(self, username: str, password: str, role: str = "user") -> dict | None:
        """创建用户，返回用户信息；用户名重复返回 None"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                now = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    "INSERT INTO users (username, hashed_password, role, created_at) VALUES (?, ?, ?, ?)",
                    (username, get_password_hash(password), role, now)
                )
                await db.commit()
                return {"username": username, "role": role, "created_at": now}
        except aiosqlite.IntegrityError:
            return None

    async def get_user(self, username: str) -> dict | None:
        """根据用户名查询用户"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE username = ?", (username,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None

    async def authenticate(self, username: str, password: str) -> dict | None:
        """验证用户名密码，成功返回用户信息"""
        user = await self.get_user(username)
        if user and verify_password(password, user["hashed_password"]):
            return user
        return None

    async def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """修改密码，验证旧密码后更新"""
        user = await self.get_user(username)
        if not user or not verify_password(old_password, user["hashed_password"]):
            return False
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET hashed_password = ? WHERE username = ?",
                (get_password_hash(new_password), username)
            )
            await db.commit()
        return True

    async def list_users(self, skip: int = 0, limit: int = 50) -> list[dict]:
        """列出用户（不含密码），支持分页"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, username, role, created_at FROM users ORDER BY id LIMIT ? OFFSET ?",
                (limit, skip)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def delete_user(self, username: str) -> bool:
        """删除用户"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM users WHERE username = ?", (username,))
            await db.commit()
            return cursor.rowcount > 0

    async def reset_password(self, username: str, new_password: str) -> bool:
        """管理员重置用户密码（无需旧密码）"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE users SET hashed_password = ? WHERE username = ?",
                (get_password_hash(new_password), username)
            )
            await db.commit()
            return cursor.rowcount > 0

    # ===================== 服务器管理 =====================

    async def register_server(self, server_id: str) -> dict:
        """注册服务器（mod连接时自动调用），已存在则更新 last_seen_at"""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            # INSERT OR IGNORE + UPDATE 保证幂等
            await db.execute(
                "INSERT OR IGNORE INTO servers (server_id, name, created_at, last_seen_at) VALUES (?, '', ?, ?)",
                (server_id, now, now)
            )
            await db.execute(
                "UPDATE servers SET last_seen_at = ? WHERE server_id = ?",
                (now, server_id)
            )
            await db.commit()
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM servers WHERE server_id = ?", (server_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row)

    async def get_server(self, server_id: str) -> dict | None:
        """查询服务器信息"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM servers WHERE server_id = ?", (server_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_server_name(self, server_id: str, name: str) -> bool:
        """修改服务器显示名称"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE servers SET name = ? WHERE server_id = ?",
                (name, server_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def list_unbound_servers(self) -> list[dict]:
        """列出没有任何绑定用户的服务器"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT s.* FROM servers s
                LEFT JOIN user_servers us ON s.server_id = us.server_id
                WHERE us.username IS NULL
                ORDER BY s.created_at DESC
            """) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # ===================== 用户-服务器绑定 =====================

    async def bind_user_to_server(self, username: str, server_id: str, role: str = "admin") -> dict | None:
        """绑定用户到服务器，返回绑定信息；重复绑定返回 None"""
        now = datetime.now(timezone.utc).isoformat()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("PRAGMA foreign_keys=ON")
                # 如果该服务器没有任何绑定，第一个绑定的自动成为 owner
                if not await self._is_server_bound(db, server_id):
                    role = "owner"
                await db.execute(
                    "INSERT INTO user_servers (username, server_id, role, bound_at) VALUES (?, ?, ?, ?)",
                    (username, server_id, role, now)
                )
                await db.commit()
                return {"username": username, "server_id": server_id, "role": role, "bound_at": now}
        except aiosqlite.IntegrityError:
            return None

    async def unbind_user_from_server(self, username: str, server_id: str) -> bool:
        """解绑用户与服务器"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            cursor = await db.execute(
                "DELETE FROM user_servers WHERE username = ? AND server_id = ?",
                (username, server_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_user_server_role(self, username: str, server_id: str) -> str | None:
        """查询用户对某服务器的角色，None表示无权限"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT role FROM user_servers WHERE username = ? AND server_id = ?",
                (username, server_id)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def list_user_servers(self, username: str) -> list[dict]:
        """列出用户绑定的所有服务器"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT us.username, us.server_id, us.role, us.bound_at,
                       s.name, s.created_at, s.last_seen_at
                FROM user_servers us
                JOIN servers s ON us.server_id = s.server_id
                WHERE us.username = ?
                ORDER BY us.bound_at
            """, (username,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def list_server_users(self, server_id: str) -> list[dict]:
        """列出服务器绑定的所有用户"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT username, role, bound_at
                FROM user_servers
                WHERE server_id = ?
                ORDER BY bound_at
            """, (server_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def is_server_bound(self, server_id: str) -> bool:
        """检查服务器是否已有任何绑定用户"""
        async with aiosqlite.connect(self.db_path) as db:
            return await self._is_server_bound(db, server_id)

    async def _is_server_bound(self, db, server_id: str) -> bool:
        """内部方法：在已有连接上检查绑定状态"""
        async with db.execute(
            "SELECT 1 FROM user_servers WHERE server_id = ? LIMIT 1",
            (server_id,)
        ) as cursor:
            return await cursor.fetchone() is not None

    # ===================== 绑定申请 =====================

    async def create_bind_request(self, username: str, server_id: str) -> dict | None:
        """创建绑定申请，同用户同服务器已有 pending 则返回 None"""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            # 检查是否已有 pending 申请
            async with db.execute(
                "SELECT 1 FROM bind_requests WHERE username = ? AND server_id = ? AND status = 'pending'",
                (username, server_id)
            ) as cursor:
                if await cursor.fetchone():
                    return None
            await db.execute(
                "INSERT INTO bind_requests (username, server_id, status, created_at) VALUES (?, ?, 'pending', ?)",
                (username, server_id, now)
            )
            await db.commit()
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bind_requests WHERE username = ? AND server_id = ? AND status = 'pending'",
                (username, server_id)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def list_pending_requests(self, server_id: str) -> list[dict]:
        """列出服务器的待审批申请"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bind_requests WHERE server_id = ? AND status = 'pending' ORDER BY created_at",
                (server_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def resolve_bind_request(self, request_id: int, approved: bool, resolved_by: str) -> dict | None:
        """审批绑定申请，返回申请信息；不存在或已处理返回 None"""
        now = datetime.now(timezone.utc).isoformat()
        status = "approved" if approved else "rejected"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            # 先查询申请
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bind_requests WHERE id = ? AND status = 'pending'",
                (request_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                request_info = dict(row)
            # 更新状态
            await db.execute(
                "UPDATE bind_requests SET status = ?, resolved_at = ?, resolved_by = ? WHERE id = ?",
                (status, now, resolved_by, request_id)
            )
            # 如果批准，自动创建绑定
            if approved:
                try:
                    await db.execute(
                        "INSERT INTO user_servers (username, server_id, role, bound_at) VALUES (?, ?, 'admin', ?)",
                        (request_info["username"], request_info["server_id"], now)
                    )
                except aiosqlite.IntegrityError:
                    pass  # 已绑定则忽略
            await db.commit()
            request_info["status"] = status
            request_info["resolved_at"] = now
            request_info["resolved_by"] = resolved_by
            return request_info

    async def get_user_pending_request(self, username: str, server_id: str) -> dict | None:
        """查询用户对某服务器的 pending 申请"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bind_requests WHERE username = ? AND server_id = ? AND status = 'pending'",
                (username, server_id)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None


user_db = UserDatabase()
