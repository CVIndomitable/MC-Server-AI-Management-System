from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api import auth, chat, memory, servers
from app.websocket import routes as ws_routes
from app.core.database import user_db
from app.services.memory import memory_service
from app.services.memory_consolidator import memory_consolidator
from app.services.command_cache import command_cache
from app.services.command_reviewer import command_reviewer
from app.services.ai_agent import ai_agent, client as anthropic_client
from app.websocket.manager import manager
from config.settings import settings
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：初始化用户数据库
    await user_db.init()
    await user_db.ensure_default_admin()

    # 启动：初始化记忆服务和后台整理任务
    try:
        await memory_service.init()
        await command_cache.init()
        command_reviewer.ai_client = anthropic_client
        await command_reviewer.init()
        await memory_consolidator.start(
            get_conversation_fn=lambda admin_id, server_id: ai_agent.conversation_history.get((admin_id, server_id), [])
        )
        logger.info("记忆系统 + 命令缓存 + 命令审核已启动")
    except Exception as e:
        logger.warning(f"记忆系统启动失败（Redis 可能未运行）: {e}")

    # 启动：WebSocket 僵死连接清理
    await manager.start_cleanup()

    yield

    # 关闭：清理资源
    await manager.stop_cleanup()
    await memory_consolidator.stop()
    await command_reviewer.close()
    await command_cache.close()
    await memory_service.close()


app = FastAPI(title="MC Admin Server", version="1.0.0", lifespan=lifespan)

# 请求体大小限制（1MB）
MAX_BODY_SIZE = 1 * 1024 * 1024

@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_BODY_SIZE:
        return JSONResponse({"detail": "请求体过大"}, status_code=413)
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(servers.router)
app.include_router(memory.router)
app.include_router(ws_routes.router)

@app.get("/")
async def root():
    return {"message": "MC Admin Server API", "version": "1.0.0"}

@app.get("/health")
async def health():
    checks = {"api": "ok"}
    try:
        if memory_service._redis:
            await memory_service._redis.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not_initialized"
    except Exception:
        checks["redis"] = "error"
    try:
        await user_db.get_user("__health_check__")
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
