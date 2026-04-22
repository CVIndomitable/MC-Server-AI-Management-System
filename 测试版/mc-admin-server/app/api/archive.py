"""档案馆 API：spark profiler 采样历史查看与 AI 分析。"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import verify_token
from app.core.database import user_db
from app.core.permissions import require_server_access
from app.services.spark_analyzer import analyze_profile
from app.websocket.manager import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/archive", tags=["archive"])


# ---------- Schemas ----------

class SparkProfileSummary(BaseModel):
    id: int
    admin_id: str
    server_id: str
    started_at: str
    stopped_at: Optional[str] = None
    start_command: Optional[str] = None
    profile_url: Optional[str] = None
    ai_model: Optional[str] = None
    ai_provider: Optional[str] = None
    analyzed_at: Optional[str] = None
    status: str
    error: Optional[str] = None


class SparkProfileDetail(SparkProfileSummary):
    stop_output: Optional[str] = None
    profile_raw: Optional[str] = None
    ai_analysis: Optional[str] = None
    ai_thinking: Optional[str] = None


class SparkProfileListResponse(BaseModel):
    items: list[SparkProfileSummary]
    total: int
    limit: int
    offset: int


class AnalyzeResponse(BaseModel):
    ok: bool
    profile: SparkProfileDetail


class MessageResponse(BaseModel):
    message: str


# ---------- Helpers ----------

def _to_summary(row: dict) -> SparkProfileSummary:
    return SparkProfileSummary(**{k: row.get(k) for k in SparkProfileSummary.model_fields})


def _to_detail(row: dict) -> SparkProfileDetail:
    return SparkProfileDetail(**{k: row.get(k) for k in SparkProfileDetail.model_fields})


# ---------- Routes ----------

@router.get("/spark/{server_id}", response_model=SparkProfileListResponse)
async def list_spark_archives(
    server_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(verify_token),
):
    admin_id = user.get("sub", "admin")
    await require_server_access(admin_id, server_id, min_role="admin")
    rows = await user_db.list_spark_profiles(server_id, limit=limit, offset=offset)
    total = await user_db.count_spark_profiles(server_id)
    return SparkProfileListResponse(
        items=[_to_summary(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/spark/{server_id}/{profile_id}", response_model=SparkProfileDetail)
async def get_spark_archive(
    server_id: str,
    profile_id: int,
    user: dict = Depends(verify_token),
):
    admin_id = user.get("sub", "admin")
    await require_server_access(admin_id, server_id, min_role="admin")
    row = await user_db.get_spark_profile(profile_id)
    if not row or row["server_id"] != server_id:
        raise HTTPException(status_code=404, detail="档案不存在")
    return _to_detail(row)


@router.post("/spark/{server_id}/{profile_id}/analyze", response_model=AnalyzeResponse)
async def analyze_spark_archive(
    server_id: str,
    profile_id: int,
    user: dict = Depends(verify_token),
):
    """触发 AI 对该档案做扩展思考分析。结果写入档案，并返回完整详情。"""
    admin_id = user.get("sub", "admin")
    await require_server_access(admin_id, server_id, min_role="admin")

    row = await user_db.get_spark_profile(profile_id)
    if not row or row["server_id"] != server_id:
        raise HTTPException(status_code=404, detail="档案不存在")
    if not row.get("profile_url"):
        raise HTTPException(status_code=400, detail="该档案缺少 spark 报告链接，无法分析")
    if row.get("status") == "analyzing":
        raise HTTPException(status_code=409, detail="该档案正在分析中，请稍候")

    # 拿当前服务器状态辅助判断（可能不在线）
    current = await ws_manager.get_status(server_id)
    server_context = current.get("data") if current else None

    await user_db.set_spark_profile_status(profile_id, "analyzing")
    try:
        result = await analyze_profile(row["profile_url"], server_context=server_context)
    except Exception as e:
        logger.error(f"spark 分析失败 profile={profile_id}: {e}", exc_info=True)
        await user_db.update_spark_profile_analysis(
            profile_id,
            analysis=None,
            thinking=None,
            model=None,
            provider=None,
            status="failed",
            error=str(e)[:500],
        )
        raise HTTPException(status_code=502, detail=f"AI 分析失败: {e}")

    updated = await user_db.update_spark_profile_analysis(
        profile_id,
        analysis=result.get("analysis") or "(模型未返回分析文本)",
        thinking=result.get("thinking"),
        model=result.get("model"),
        provider=result.get("provider"),
        profile_raw=result.get("profile_raw"),
        status="analyzed",
        error=result.get("fetch_error"),
    )
    if not updated:
        raise HTTPException(status_code=500, detail="档案更新失败")
    return AnalyzeResponse(ok=True, profile=_to_detail(updated))


@router.delete("/spark/{server_id}/{profile_id}", response_model=MessageResponse)
async def delete_spark_archive(
    server_id: str,
    profile_id: int,
    user: dict = Depends(verify_token),
):
    admin_id = user.get("sub", "admin")
    await require_server_access(admin_id, server_id, min_role="admin")
    row = await user_db.get_spark_profile(profile_id)
    if not row or row["server_id"] != server_id:
        raise HTTPException(status_code=404, detail="档案不存在")
    ok = await user_db.delete_spark_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=500, detail="删除失败")
    return MessageResponse(message="已删除")
