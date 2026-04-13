from fastapi import APIRouter, Depends, HTTPException
from app.models.schemas import (
    MemoryUpdateRequest,
    MemoryResponse,
    MemoryBackupListResponse,
    MemoryBackupItem,
    MemoryRollbackRequest,
    MemoryConsolidationStatus,
)
from app.core.auth import verify_token
from app.services.memory import memory_service
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


# ============ 全局记忆 ============

@router.get("/global", response_model=MemoryResponse)
async def get_global_memory(user: dict = Depends(verify_token)):
    meta = await memory_service.get_memory_with_meta("global")
    if not meta:
        return MemoryResponse(content="", updated_at=None)
    return MemoryResponse(
        content=meta["content"],
        updated_at=datetime.fromtimestamp(meta["updated_at"]) if meta.get("updated_at") else None,
    )


@router.put("/global", response_model=dict)
async def update_global_memory(
    request: MemoryUpdateRequest, user: dict = Depends(verify_token)
):
    result = await memory_service.set_memory("global", "", request.content)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "全局记忆已更新"}


# ============ 管理员记忆 ============

@router.get("/admin/{admin_id}", response_model=MemoryResponse)
async def get_admin_memory(admin_id: str, user: dict = Depends(verify_token)):
    meta = await memory_service.get_memory_with_meta("admin", admin_id)
    if not meta:
        return MemoryResponse(content="", updated_at=None)
    return MemoryResponse(
        content=meta["content"],
        updated_at=datetime.fromtimestamp(meta["updated_at"]) if meta.get("updated_at") else None,
    )


@router.put("/admin/{admin_id}", response_model=dict)
async def update_admin_memory(
    admin_id: str, request: MemoryUpdateRequest, user: dict = Depends(verify_token)
):
    result = await memory_service.set_memory("admin", admin_id, request.content)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "管理员记忆已更新"}


# ============ 服务器记忆 ============

@router.get("/server/{server_id}", response_model=MemoryResponse)
async def get_server_memory(server_id: str, user: dict = Depends(verify_token)):
    meta = await memory_service.get_memory_with_meta("server", server_id)
    if not meta:
        return MemoryResponse(content="", updated_at=None)
    return MemoryResponse(
        content=meta["content"],
        updated_at=datetime.fromtimestamp(meta["updated_at"]) if meta.get("updated_at") else None,
    )


@router.put("/server/{server_id}", response_model=dict)
async def update_server_memory(
    server_id: str, request: MemoryUpdateRequest, user: dict = Depends(verify_token)
):
    result = await memory_service.set_memory("server", server_id, request.content)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "服务器记忆已更新"}


# ============ 备份与回滚 ============

@router.get("/backup/{mem_type}/{mem_id}", response_model=MemoryBackupListResponse)
async def list_backups(mem_type: str, mem_id: str, user: dict = Depends(verify_token)):
    if mem_type not in ("global", "admin", "server"):
        raise HTTPException(status_code=400, detail="无效的记忆类型")
    raw_list = await memory_service.list_backups(mem_type, mem_id)
    backups = [
        MemoryBackupItem(
            version=item["version"],
            timestamp=datetime.fromtimestamp(item["timestamp"]),
            content_preview=item["content_preview"],
        )
        for item in raw_list
    ]
    return MemoryBackupListResponse(backups=backups)


@router.post("/rollback/{mem_type}/{mem_id}", response_model=dict)
async def rollback_memory(
    mem_type: str,
    mem_id: str,
    request: MemoryRollbackRequest,
    user: dict = Depends(verify_token),
):
    if mem_type not in ("global", "admin", "server"):
        raise HTTPException(status_code=400, detail="无效的记忆类型")
    result = await memory_service.rollback(mem_type, mem_id, request.version)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": f"已回滚到版本 {request.version}"}
