import aiosqlite
import os
import logging
from datetime import datetime
from app.core.auth import get_password_hash, verify_password

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "users.db")


class UserDatabase:
    def __init__(self):
        self.db_path = DB_PATH

    async def init(self):
        """初始化数据库，创建用户表"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL
                )
            """)
            await db.commit()
        logger.info(f"用户数据库已初始化: {self.db_path}")

    async def ensure_default_admin(self):
        """首次启动时创建默认管理员账号"""
        admin = await self.get_user("admin")
        if not admin:
            await self.create_user("admin", "admin123", role="admin")
            logger.info("已创建默认管理员账号 admin/admin123，请尽快修改密码")

    async def create_user(self, username: str, password: str, role: str = "user") -> dict | None:
        """创建用户，返回用户信息；用户名重复返回 None"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                now = datetime.utcnow().isoformat()
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

    async def list_users(self) -> list[dict]:
        """列出所有用户（不含密码）"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id, username, role, created_at FROM users ORDER BY id") as cursor:
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


user_db = UserDatabase()
