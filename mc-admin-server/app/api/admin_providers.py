"""LLM API 供应商管理（仅管理员）"""
from fastapi import APIRouter, Depends, HTTPException
from app.models.schemas import (
    ApiProviderInfo, ApiProviderListResponse,
    ApiProviderCreateRequest, ApiProviderUpdateRequest,
)
from app.core.auth import verify_token
from app.core.database import user_db
from app.services.ai_client import provider_pool
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/providers", tags=["admin-providers"])


def _require_admin(user: dict):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可管理 LLM 供应商")


def _mask_key(key: str) -> str:
    if not key:
        return ""
    return key[-4:] if len(key) >= 4 else "*" * len(key)


def _to_info(row: dict) -> ApiProviderInfo:
    return ApiProviderInfo(
        id=row["id"],
        name=row["name"],
        base_url=row["base_url"],
        api_key_tail=_mask_key(row["api_key"]),
        priority=row["priority"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("", response_model=ApiProviderListResponse)
async def list_providers(current_user: dict = Depends(verify_token)):
    """列出所有 LLM 供应商（不含完整 api_key）"""
    _require_admin(current_user)
    rows = await user_db.list_providers(only_enabled=False)
    return ApiProviderListResponse(providers=[_to_info(r) for r in rows])


@router.post("", response_model=ApiProviderInfo)
async def create_provider(
    req: ApiProviderCreateRequest,
    current_user: dict = Depends(verify_token),
):
    """新增 LLM 供应商"""
    _require_admin(current_user)
    row = await user_db.create_provider(
        name=req.name.strip(),
        base_url=req.base_url.strip(),
        api_key=req.api_key.strip(),
        priority=req.priority,
        enabled=req.enabled,
    )
    if not row:
        raise HTTPException(status_code=409, detail="供应商名称已存在")
    await provider_pool.reload()
    logger.info(f"[{current_user.get('sub')}] 创建 LLM 供应商: {req.name}")
    return _to_info(row)


@router.put("/{provider_id}", response_model=ApiProviderInfo)
async def update_provider(
    provider_id: int,
    req: ApiProviderUpdateRequest,
    current_user: dict = Depends(verify_token),
):
    """更新供应商；api_key 留空表示保留原值"""
    _require_admin(current_user)
    existing = await user_db.get_provider(provider_id)
    if not existing:
        raise HTTPException(status_code=404, detail="供应商不存在")
    # 空字符串也视为不修改
    api_key = req.api_key.strip() if req.api_key else None
    row = await user_db.update_provider(
        provider_id,
        name=req.name.strip() if req.name else None,
        base_url=req.base_url.strip() if req.base_url else None,
        api_key=api_key or None,
        priority=req.priority,
        enabled=req.enabled,
    )
    if not row:
        raise HTTPException(status_code=409, detail="更新失败，可能名称冲突")
    await provider_pool.reload()
    logger.info(f"[{current_user.get('sub')}] 更新 LLM 供应商 #{provider_id}")
    return _to_info(row)


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: int,
    current_user: dict = Depends(verify_token),
):
    """删除供应商"""
    _require_admin(current_user)
    ok = await user_db.delete_provider(provider_id)
    if not ok:
        raise HTTPException(status_code=404, detail="供应商不存在")
    await provider_pool.reload()
    logger.info(f"[{current_user.get('sub')}] 删除 LLM 供应商 #{provider_id}")
    return {"message": "已删除"}
