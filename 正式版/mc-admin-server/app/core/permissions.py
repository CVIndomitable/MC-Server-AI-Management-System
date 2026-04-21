from fastapi import HTTPException
from app.core.database import user_db

ROLE_HIERARCHY = {"owner": 2, "admin": 1}


async def require_server_access(username: str, server_id: str, min_role: str = "admin") -> str:
    """检查用户对服务器的访问权限，返回用户角色；权限不足抛出 403"""
    role = await user_db.get_user_server_role(username, server_id)
    if role is None:
        raise HTTPException(status_code=403, detail="你没有该服务器的访问权限")
    if ROLE_HIERARCHY.get(role, 0) < ROLE_HIERARCHY.get(min_role, 0):
        raise HTTPException(status_code=403, detail="权限不足")
    return role
