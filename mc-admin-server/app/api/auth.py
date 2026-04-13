from fastapi import APIRouter, HTTPException, Depends
from app.models.schemas import (
    LoginRequest, Token, RegisterRequest, ChangePasswordRequest,
    ResetPasswordRequest, UserInfo, UserListResponse
)
from app.core.auth import create_access_token, verify_token
from app.core.database import user_db

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(request: LoginRequest):
    """用户登录"""
    user = await user_db.authenticate(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    access_token = create_access_token({"sub": user["username"], "role": user["role"]})
    return Token(access_token=access_token)


@router.post("/register", response_model=UserInfo)
async def register(request: RegisterRequest, current_user: dict = Depends(verify_token)):
    """注册新用户（仅管理员）"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可创建用户")
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="密码长度不能少于6位")
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
        raise HTTPException(status_code=403, detail="仅管理员可重置密码")
    if len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于6位")
    success = await user_db.reset_password(username, request.new_password)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"message": f"用户 {username} 的密码已重置"}


@router.get("/users", response_model=UserListResponse)
async def list_users(current_user: dict = Depends(verify_token)):
    """获取用户列表（仅管理员）"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可查看用户列表")
    users = await user_db.list_users()
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
    return {"message": f"用户 {username} 已删除"}
