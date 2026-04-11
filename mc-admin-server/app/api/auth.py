from fastapi import APIRouter, HTTPException
from app.models.schemas import LoginRequest, Token
from app.core.auth import create_access_token, verify_password, get_password_hash

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# 临时硬编码用户，生产环境应使用数据库
USERS_DB = {
    "admin": {
        "username": "admin",
        "hashed_password": get_password_hash("admin123")
    }
}

@router.post("/login", response_model=Token)
async def login(request: LoginRequest):
    user = USERS_DB.get(request.username)
    if not user or not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    access_token = create_access_token({"sub": request.username})
    return Token(access_token=access_token)
