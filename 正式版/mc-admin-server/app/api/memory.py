from fastapi import APIRouter, Depends, HTTPException
from app.models.schemas import (
    MemoryEntry,
    MemoryUpdateRequest,
    MemoryResponse,
    MemoryBackupListResponse,
    MemoryBackupItem,
    MemoryRollbackRequest,
)
from app.core.auth import verify_token
from app.core.permissions import require_server_access
from app.services.memory import memory_service, VALID_TAGS
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


def _build_memory_response(meta: dict) -> MemoryResponse:
    """从 Redis 元数据构建 MemoryResponse（含 entries）"""
    entries = None
    if meta.get("entries"):
        entries = [
            MemoryEntry(
                id=e.get("id"),
                tags=e.get("tags", []),
                content=e.get("content", ""),
                pinned=e.get("pinned", False),
            )
            for e in meta["entries"]
        ]
    return MemoryResponse(
        content=meta["content"],
        entries=entries,
        updated_at=datetime.fromtimestamp(meta["updated_at"]) if meta.get("updated_at") else None,
    )


def _validate_entry_tags(entries: list[MemoryEntry]):
    """校验 entries 中的 tags 是否合法"""
    for entry in entries:
        invalid = set(entry.tags) - VALID_TAGS
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"无效的标签: {', '.join(invalid)}。合法标签: {', '.join(sorted(VALID_TAGS))}",
            )


async def _save_memory(mem_type: str, mem_id: str, request: MemoryUpdateRequest) -> dict:
    """统一保存逻辑：有 entries 用结构化存储，否则用纯文本"""
    if request.entries:
        _validate_entry_tags(request.entries)
        entries_dicts = [e.model_dump() for e in request.entries]
        return await memory_service.set_structured_memory(mem_type, mem_id, entries_dicts)
    else:
        return await memory_service.set_memory(mem_type, mem_id, request.content)


def _check_memory_permission(user: dict, mem_type: str, mem_id: str):
    """检查记忆访问权限（同步检查，不含需要await的服务器权限）"""
    username = user.get("sub")
    role = user.get("role")
    if mem_type == "global" and role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作全局记忆")
    if mem_type == "admin" and username != mem_id and role != "admin":
        raise HTTPException(status_code=403, detail="无权操作该管理员的记忆")


# ============ 全局记忆 ============

@router.get("/global", response_model=MemoryResponse)
async def get_global_memory(user: dict = Depends(verify_token)):
    meta = await memory_service.get_memory_with_meta("global")
    if not meta:
        return MemoryResponse(content="", updated_at=None)
    return _build_memory_response(meta)


@router.put("/global", response_model=dict)
async def update_global_memory(
    request: MemoryUpdateRequest, user: dict = Depends(verify_token)
):
    _check_memory_permission(user, "global", "")
    result = await _save_memory("global", "", request)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "全局记忆已更新"}


# ============ 管理员记忆 ============

@router.get("/admin/{admin_id}", response_model=MemoryResponse)
async def get_admin_memory(admin_id: str, user: dict = Depends(verify_token)):
    _check_memory_permission(user, "admin", admin_id)
    meta = await memory_service.get_memory_with_meta("admin", admin_id)
    if not meta:
        return MemoryResponse(content="", updated_at=None)
    return _build_memory_response(meta)


@router.put("/admin/{admin_id}", response_model=dict)
async def update_admin_memory(
    admin_id: str, request: MemoryUpdateRequest, user: dict = Depends(verify_token)
):
    _check_memory_permission(user, "admin", admin_id)
    result = await _save_memory("admin", admin_id, request)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "管理员记忆已更新"}


# ============ 服务器记忆 ============

@router.get("/server/{server_id}", response_model=MemoryResponse)
async def get_server_memory(server_id: str, user: dict = Depends(verify_token)):
    username = user.get("sub")
    await require_server_access(username, server_id)
    meta = await memory_service.get_memory_with_meta("server", server_id)
    if not meta:
        return MemoryResponse(content="", updated_at=None)
    return _build_memory_response(meta)


@router.put("/server/{server_id}", response_model=dict)
async def update_server_memory(
    server_id: str, request: MemoryUpdateRequest, user: dict = Depends(verify_token)
):
    username = user.get("sub")
    await require_server_access(username, server_id)
    result = await _save_memory("server", server_id, request)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "服务器记忆已更新"}


# ============ 备份与回滚 ============

@router.get("/backup/{mem_type}/{mem_id}", response_model=MemoryBackupListResponse)
async def list_backups(mem_type: str, mem_id: str, user: dict = Depends(verify_token)):
    if mem_type not in ("global", "admin", "server"):
        raise HTTPException(status_code=400, detail="无效的记忆类型")
    _check_memory_permission(user, mem_type, mem_id)
    if mem_type == "server":
        username = user.get("sub")
        await require_server_access(username, mem_id)
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
    _check_memory_permission(user, mem_type, mem_id)
    if mem_type == "server":
        username = user.get("sub")
        await require_server_access(username, mem_id)
    result = await memory_service.rollback(mem_type, mem_id, request.version)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": f"已回滚到版本 {request.version}"}
