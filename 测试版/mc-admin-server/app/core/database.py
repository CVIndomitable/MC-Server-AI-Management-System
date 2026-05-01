import aiosqlite
import json
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
        try:
            os.chmod(db_dir, 0o700)
        except (OSError, PermissionError):
            pass  # 容器环境下可能无权限修改，跳过
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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS api_providers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    base_url TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 100,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    model_map TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # 已有库的老表补 model_map 列（JSON 映射：canonical 模型名 → 该 provider 实际模型名）
            try:
                await db.execute("ALTER TABLE api_providers ADD COLUMN model_map TEXT")
            except aiosqlite.OperationalError:
                pass  # 列已存在
            # Spark profiler 档案馆：每次 /spark profiler start→stop 一个会话
            # status: running / stopped / analyzing / analyzed / failed
            await db.execute("""
                CREATE TABLE IF NOT EXISTS spark_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    stopped_at TEXT,
                    start_command TEXT,
                    stop_output TEXT,
                    profile_url TEXT,
                    profile_raw TEXT,
                    ai_analysis TEXT,
                    ai_thinking TEXT,
                    ai_model TEXT,
                    ai_provider TEXT,
                    analyzed_at TEXT,
                    status TEXT NOT NULL DEFAULT 'running',
                    error TEXT,
                    FOREIGN KEY (server_id) REFERENCES servers(server_id) ON DELETE CASCADE
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_spark_server_time "
                "ON spark_profiles(server_id, started_at DESC)"
            )
            await db.commit()
        logger.info(f"数据库已初始化: {self.db_path}")

    async def ensure_default_admin(self):
        """首次启动时创建默认管理员账号（使用随机密码）。
        密码仅写入数据目录下的 initial_admin_password.txt（权限 600），
        不进日志，避免被聚合/备份系统泄露。
        """
        admin = await self.get_user("admin")
        if not admin:
            import secrets
            default_password = secrets.token_urlsafe(16)
            await self.create_user("admin", default_password, role="admin")
            pwd_file = os.path.join(os.path.dirname(self.db_path), "initial_admin_password.txt")
            try:
                # 先创建空文件再 chmod，避免密码以默认 umask 短暂可读
                fd = os.open(pwd_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(default_password + "\n")
                logger.warning(
                    f"已创建默认管理员 admin；初始密码已写入 {pwd_file} (权限 600)。"
                    "请尽快登录修改密码，并删除该文件。"
                )
            except OSError as e:
                # 写文件失败 → 只能一次性打日志，否则管理员拿不到密码
                logger.error(f"无法写入初始密码文件 ({e})，回退到一次性日志输出")
                logger.warning(f"初始管理员密码: {default_password}  <-- 仅此一次")

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

                # 使用事务确保原子性
                async with db.execute("BEGIN IMMEDIATE"):
                    # 如果该服务器没有任何绑定，第一个绑定的自动成为 owner
                    async with db.execute(
                        "SELECT COUNT(*) FROM user_servers WHERE server_id = ?", (server_id,)
                    ) as cursor:
                        row = await cursor.fetchone()
                        if row[0] == 0:
                            role = "owner"

                    # 如果是 owner，检查是否已存在 owner
                    if role == "owner":
                        async with db.execute(
                            "SELECT COUNT(*) FROM user_servers WHERE server_id = ? AND role = 'owner'",
                            (server_id,)
                        ) as cursor:
                            row = await cursor.fetchone()
                            if row[0] > 0:
                                return None  # 已存在 owner

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

    # ===================== LLM API 供应商 =====================

    @staticmethod
    def _row_to_provider(row) -> dict:
        """把 sqlite row 转成 dict，同时把 model_map JSON 字段解析成 dict"""
        d = dict(row)
        raw = d.get("model_map")
        if raw:
            try:
                d["model_map"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"provider #{d.get('id')} model_map JSON 解析失败，忽略")
                d["model_map"] = None
        else:
            d["model_map"] = None
        return d

    async def list_providers(self, only_enabled: bool = False) -> list[dict]:
        """列出所有 API 供应商，按 priority 升序（数字小=优先级高）"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            sql = "SELECT * FROM api_providers"
            if only_enabled:
                sql += " WHERE enabled = 1"
            sql += " ORDER BY priority ASC, id ASC"
            async with db.execute(sql) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_provider(row) for row in rows]

    async def get_provider(self, provider_id: int) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM api_providers WHERE id = ?", (provider_id,)) as cursor:
                row = await cursor.fetchone()
                return self._row_to_provider(row) if row else None

    async def create_provider(
        self, name: str, base_url: str, api_key: str,
        priority: int = 100, enabled: bool = True,
        model_map: dict | None = None,
    ) -> dict | None:
        """创建 API 供应商；name 重复返回 None"""
        now = datetime.now(timezone.utc).isoformat()
        map_json = json.dumps(model_map, ensure_ascii=False) if model_map else None
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "INSERT INTO api_providers (name, base_url, api_key, priority, enabled, model_map, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, base_url, api_key, priority, 1 if enabled else 0, map_json, now, now),
                )
                await db.commit()
                return await self.get_provider(cursor.lastrowid)
        except aiosqlite.IntegrityError:
            return None

    async def update_provider(
        self, provider_id: int,
        name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        priority: int | None = None,
        enabled: bool | None = None,
        model_map: dict | None = None,
        clear_model_map: bool = False,
    ) -> dict | None:
        """更新 API 供应商；api_key 传 None 表示不改；model_map 传 None 且 clear_model_map=False 表示不改"""
        fields, values = [], []
        if name is not None:
            fields.append("name = ?"); values.append(name)
        if base_url is not None:
            fields.append("base_url = ?"); values.append(base_url)
        if api_key is not None:
            fields.append("api_key = ?"); values.append(api_key)
        if priority is not None:
            fields.append("priority = ?"); values.append(priority)
        if enabled is not None:
            fields.append("enabled = ?"); values.append(1 if enabled else 0)
        if clear_model_map:
            fields.append("model_map = ?"); values.append(None)
        elif model_map is not None:
            fields.append("model_map = ?"); values.append(json.dumps(model_map, ensure_ascii=False))
        if not fields:
            return await self.get_provider(provider_id)

        # 构建参数化查询
        set_clause = ", ".join(f"{field.split(' = ')[0]} = ?" for field in fields)
        fields.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())
        values.append(provider_id)

        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    f"UPDATE api_providers SET {set_clause}, updated_at = ? WHERE id = ?", values
                )
                await db.commit()
                if cursor.rowcount == 0:
                    return None
            return await self.get_provider(provider_id)
        except aiosqlite.IntegrityError:
            return None  # name 冲突

    async def delete_provider(self, provider_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM api_providers WHERE id = ?", (provider_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def count_providers(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM api_providers") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    # ===================== Spark Profiler 档案 =====================

    async def create_spark_profile(
        self, admin_id: str, server_id: str, start_command: str | None
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO spark_profiles (admin_id, server_id, started_at, start_command, status) "
                "VALUES (?, ?, ?, ?, 'running')",
                (admin_id, server_id, now, start_command),
            )
            await db.commit()
            return await self.get_spark_profile(cursor.lastrowid)

    async def stop_spark_profile(
        self, profile_id: int, profile_url: str | None, stop_output: str | None
    ) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE spark_profiles SET stopped_at=?, profile_url=?, stop_output=?, status='stopped' "
                "WHERE id=? AND status='running'",
                (now, profile_url, stop_output, profile_id),
            )
            await db.commit()
            if cursor.rowcount == 0:
                return None
        return await self.get_spark_profile(profile_id)

    async def find_running_spark_profile(self, server_id: str) -> dict | None:
        """找该服务器最近一个 running 档案（用于 stop 时关联）"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM spark_profiles WHERE server_id=? AND status='running' "
                "ORDER BY started_at DESC LIMIT 1",
                (server_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_spark_profile(self, profile_id: int) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM spark_profiles WHERE id=?", (profile_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def list_spark_profiles(
        self, server_id: str, limit: int = 20, offset: int = 0,
        include_raw: bool = False,
    ) -> list[dict]:
        # 列表默认不返回大字段，省带宽
        cols = (
            "id, admin_id, server_id, started_at, stopped_at, start_command, "
            "profile_url, ai_model, ai_provider, analyzed_at, status, error"
        )
        if include_raw:
            cols = "*"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT {cols} FROM spark_profiles WHERE server_id=? "
                "ORDER BY started_at DESC LIMIT ? OFFSET ?",
                (server_id, limit, offset),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def count_spark_profiles(self, server_id: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM spark_profiles WHERE server_id=?", (server_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def update_spark_profile_analysis(
        self, profile_id: int,
        analysis: str | None = None,
        thinking: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        profile_raw: str | None = None,
        status: str = "analyzed",
        error: str | None = None,
    ) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        fields, values = [], []
        fields.append("ai_analysis=?"); values.append(analysis)
        fields.append("ai_thinking=?"); values.append(thinking)
        fields.append("ai_model=?"); values.append(model)
        fields.append("ai_provider=?"); values.append(provider)
        if profile_raw is not None:
            fields.append("profile_raw=?"); values.append(profile_raw)
        fields.append("analyzed_at=?"); values.append(now)
        fields.append("status=?"); values.append(status)
        fields.append("error=?"); values.append(error)
        values.append(profile_id)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"UPDATE spark_profiles SET {', '.join(fields)} WHERE id=?", values
            )
            await db.commit()
            if cursor.rowcount == 0:
                return None
        return await self.get_spark_profile(profile_id)

    async def set_spark_profile_status(self, profile_id: int, status: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE spark_profiles SET status=? WHERE id=?", (status, profile_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_spark_profile(self, profile_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM spark_profiles WHERE id=?", (profile_id,)
            )
            await db.commit()
            return cursor.rowcount > 0


user_db = UserDatabase()
