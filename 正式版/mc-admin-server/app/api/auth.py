from fastapi import APIRouter, HTTPException, Depends, Request, Query
from app.models.schemas import (
    LoginRequest, Token, RegisterRequest, ChangePasswordRequest,
    ResetPasswordRequest, UserInfo, UserListResponse
)
from app.core.auth import create_access_token, verify_token
from app.core.database import user_db
from app.services.rate_limiter import check_and_increment
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# 登录频率限制
# 同时限制 per-IP 与 per-username，代理场景下单一 IP 仍无法对全库用户暴破
# 走 Redis 共享计数（多实例部署）；Redis 不可用时自动降级到进程内存
_LOGIN_RATE_LIMIT_IP = 30        # 单一 IP 每分钟 30 次（容忍代理/NAT）
_LOGIN_RATE_LIMIT_USER = 5       # 单一用户名每分钟 5 次
_LOGIN_RATE_WINDOW = 60


async def _check_login_rate(request: Request, username: str):
    client_ip = request.client.host if request.client else "unknown"
    for key, limit in (
        (f"login:ip:{client_ip}", _LOGIN_RATE_LIMIT_IP),
        (f"login:user:{username.lower()}", _LOGIN_RATE_LIMIT_USER),
    ):
        if await check_and_increment(key, limit, _LOGIN_RATE_WINDOW):
            raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")


@router.post("/login", response_model=Token)
async def login(request: LoginRequest, http_request: Request):
    """用户登录"""
    await _check_login_rate(http_request, request.username)
    client_ip = http_request.client.host if http_request.client else "unknown"
    user = await user_db.authenticate(request.username, request.password)
    if not user:
        logger.warning(f"登录失败: user={request.username}, ip={client_ip}")
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    logger.info(f"登录成功: user={request.username}, ip={client_ip}")
    access_token = create_access_token({"sub": user["username"], "role": user["role"]})
    return Token(access_token=access_token)


@router.post("/register", response_model=UserInfo)
async def register(request: RegisterRequest, current_user: dict = Depends(verify_token)):
    """注册新用户（仅管理员）"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可创建用户")
    if request.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="角色只能是 admin 或 user")
    user = await user_db.create_user(request.username, request.password, request.role)
    if not user:
        raise HTTPException(status_code=409, detail="用户名已存在")
    return UserInfo(**user)


@router.put("/password")
async def change_password(request: ChangePasswordRequest, current_user: dict = Depends(verify_token)):
    """修改自己的密码"""
    if len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于6位")
    username = current_user.get("sub")
    success = await user_db.change_password(username, request.old_password, request.new_password)
    if not success:
        raise HTTPException(status_code=400, detail="旧密码不正确")
    return {"message": "密码修改成功"}


@router.put("/users/{username}/password")
async def reset_password(username: str, request: ResetPasswordRequest, current_user: dict = Depends(verify_token)):
    """管理员重置指定用户的密码（无需旧密码）"""
    if current_user.get("role") != "admin":
        logger.warning(f"越权操作: user={current_user.get('sub')} 尝试重置 {username} 的密码")
        raise HTTPException(status_code=403, detail="仅管理员可重置密码")
    if len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于6位")
    success = await user_db.reset_password(username, request.new_password)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    logger.info(f"管理员 {current_user.get('sub')} 重置了用户 {username} 的密码")
    return {"message": f"用户 {username} 的密码已重置"}


@router.get("/users", response_model=UserListResponse)
async def list_users(
    current_user: dict = Depends(verify_token),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """获取用户列表（仅管理员，支持分页）"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可查看用户列表")
    users = await user_db.list_users(skip=skip, limit=limit)
    return UserListResponse(users=[
        UserInfo(username=u["username"], role=u["role"], created_at=u["created_at"])
        for u in users
    ])


@router.delete("/users/{username}")
async def delete_user(username: str, current_user: dict = Depends(verify_token)):
    """删除用户（仅管理员，不能删除自己）"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可删除用户")
    if current_user.get("sub") == username:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    success = await user_db.delete_user(username)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    logger.info(f"管理员 {current_user.get('sub')} 删除了用户 {username}")
    return {"message": f"用户 {username} 已删除"}
