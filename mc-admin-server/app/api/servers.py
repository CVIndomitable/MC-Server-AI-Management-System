from fastapi import APIRouter, HTTPException, Depends
from app.models.schemas import (
    UserServerInfo, UserServerListResponse, UnboundServerListResponse,
    ServerInfo, BindRequestInfo, BindRequestListResponse,
    UpdateServerNameRequest, ServerUserInfo, ServerUserListResponse
)
from app.core.auth import verify_token
from app.core.database import user_db
from app.core.permissions import require_server_access
from app.websocket.manager import manager
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/servers", tags=["servers"])


@router.get("/my", response_model=UserServerListResponse)
async def list_my_servers(user: dict = Depends(verify_token)):
    """获取当前用户绑定的服务器列表"""
    username = user.get("sub")
    rows = await user_db.list_user_servers(username)
    servers = []
    for r in rows:
        online = await manager.is_online(r["server_id"])
        servers.append(UserServerInfo(
            server_id=r["server_id"],
            name=r["name"] or r["server_id"],
            role=r["role"],
            online=online,
            bound_at=r["bound_at"],
        ))
    return UserServerListResponse(servers=servers)


@router.get("/unbound", response_model=UnboundServerListResponse)
async def list_unbound_servers(user: dict = Depends(verify_token)):
    """获取未绑定任何用户的服务器列表（仅系统admin）"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可查看未绑定服务器")
    rows = await user_db.list_unbound_servers()
    servers = []
    for r in rows:
        online = await manager.is_online(r["server_id"])
        servers.append(ServerInfo(
            server_id=r["server_id"],
            name=r["name"] or r["server_id"],
            online=online,
            created_at=r["created_at"],
            last_seen_at=r.get("last_seen_at"),
        ))
    return UnboundServerListResponse(servers=servers)


@router.post("/{server_id}/bind", response_model=UserServerInfo)
async def bind_server(server_id: str, user: dict = Depends(verify_token)):
    """绑定服务器：无人绑定→直接成为owner；已有owner→自动创建申请"""
    username = user.get("sub")

    # 检查服务器是否存在
    server = await user_db.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    # 检查是否已绑定
    existing_role = await user_db.get_user_server_role(username, server_id)
    if existing_role:
        raise HTTPException(status_code=409, detail=f"你已绑定该服务器，角色: {existing_role}")

    # 如果服务器没有任何绑定 → 直接绑定为 owner
    if not await user_db.is_server_bound(server_id):
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="仅系统管理员可首次绑定服务器")
        result = await user_db.bind_user_to_server(username, server_id)
        if not result:
            raise HTTPException(status_code=500, detail="绑定失败")
        online = await manager.is_online(server_id)
        return UserServerInfo(
            server_id=server_id,
            name=server["name"] or server_id,
            role=result["role"],
            online=online,
            bound_at=result["bound_at"],
        )

    # 服务器已有 owner → 创建绑定申请
    existing_request = await user_db.get_user_pending_request(username, server_id)
    if existing_request:
        raise HTTPException(status_code=409, detail="你已有待审批的绑定申请")

    request = await user_db.create_bind_request(username, server_id)
    if not request:
        raise HTTPException(status_code=409, detail="创建申请失败")

    raise HTTPException(
        status_code=202,
        detail="已提交绑定申请，等待主管理员审批"
    )


@router.get("/{server_id}/requests", response_model=BindRequestListResponse)
async def list_bind_requests(server_id: str, user: dict = Depends(verify_token)):
    """查看服务器待审批的绑定申请（仅owner）"""
    username = user.get("sub")
    await require_server_access(username, server_id, min_role="owner")
    rows = await user_db.list_pending_requests(server_id)
    requests = [BindRequestInfo(**r) for r in rows]
    return BindRequestListResponse(requests=requests)


@router.post("/{server_id}/requests/{request_id}/approve")
async def approve_bind_request(server_id: str, request_id: int, user: dict = Depends(verify_token)):
    """批准绑定申请（仅owner）"""
    username = user.get("sub")
    await require_server_access(username, server_id, min_role="owner")
    result = await user_db.resolve_bind_request(request_id, approved=True, resolved_by=username)
    if not result:
        raise HTTPException(status_code=404, detail="申请不存在或已处理")
    return {"message": f"已批准 {result['username']} 的绑定申请"}


@router.post("/{server_id}/requests/{request_id}/reject")
async def reject_bind_request(server_id: str, request_id: int, user: dict = Depends(verify_token)):
    """拒绝绑定申请（仅owner）"""
    username = user.get("sub")
    await require_server_access(username, server_id, min_role="owner")
    result = await user_db.resolve_bind_request(request_id, approved=False, resolved_by=username)
    if not result:
        raise HTTPException(status_code=404, detail="申请不存在或已处理")
    return {"message": f"已拒绝 {result['username']} 的绑定申请"}


@router.delete("/{server_id}/unbind/{username}")
async def unbind_user(server_id: str, username: str, user: dict = Depends(verify_token)):
    """将其他管理员从服务器解绑（仅owner）"""
    current_user = user.get("sub")
    await require_server_access(current_user, server_id, min_role="owner")

    if username == current_user:
        raise HTTPException(status_code=400, detail="主管理员不能解绑自己")

    success = await user_db.unbind_user_from_server(username, server_id)
    if not success:
        raise HTTPException(status_code=404, detail="该用户未绑定此服务器")
    return {"message": f"已将 {username} 从服务器解绑"}


@router.put("/{server_id}/name")
async def update_server_name(server_id: str, request: UpdateServerNameRequest, user: dict = Depends(verify_token)):
    """修改服务器显示名称（仅owner）"""
    username = user.get("sub")
    await require_server_access(username, server_id, min_role="owner")

    if not request.name.strip():
        raise HTTPException(status_code=400, detail="名称不能为空")

    success = await user_db.update_server_name(server_id, request.name.strip())
    if not success:
        raise HTTPException(status_code=404, detail="服务器不存在")
    return {"message": f"服务器名称已更新为: {request.name.strip()}"}


@router.get("/{server_id}/users", response_model=ServerUserListResponse)
async def list_server_users(server_id: str, user: dict = Depends(verify_token)):
    """查看服务器管理员列表（绑定用户可查看）"""
    username = user.get("sub")
    await require_server_access(username, server_id, min_role="admin")
    rows = await user_db.list_server_users(server_id)
    users = [ServerUserInfo(**r) for r in rows]
    return ServerUserListResponse(users=users)
