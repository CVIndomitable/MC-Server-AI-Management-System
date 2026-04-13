from fastapi import APIRouter, Depends, HTTPException, Query
from app.models.schemas import ChatRequest, ChatResponse, ServerStatus, ReviewInfo
from app.models.review import ReviewDecision
from app.core.auth import verify_token
from app.core.permissions import require_server_access
from app.services.ai_agent import ai_agent
from app.services.memory import memory_service
from app.services.command_reviewer import command_reviewer
from app.websocket.manager import manager
from config.settings import settings
from datetime import datetime
from typing import Literal
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


def _extract_command_from_tool_call(tool_name: str, tool_input: dict) -> str:
    """从工具调用中提取实际要执行的MC命令"""
    if tool_name == "execute_command":
        return tool_input.get("command", "")
    elif tool_name == "kick_player":
        cmd = f"/kick {tool_input['player']}"
        if "reason" in tool_input:
            cmd += f" {tool_input['reason']}"
        return cmd
    elif tool_name == "op_player":
        return f"/op {tool_input['player']}"
    elif tool_name == "deop_player":
        return f"/deop {tool_input['player']}"
    elif tool_name == "get_status":
        return "get_status"
    elif tool_name == "restart_server":
        return "restart_server"
    elif tool_name == "broadcast":
        return f"/say {tool_input['message']}"
    return tool_name


async def _execute_tool(server_id: str, tool_name: str, tool_input: dict, current_status: dict) -> dict:
    """执行单个工具调用，返回结果"""
    if tool_name == "execute_command":
        return await manager.send_command(
            server_id, "execute", {"command": tool_input["command"]}
        )
    elif tool_name == "kick_player":
        cmd = f"/kick {tool_input['player']}"
        if "reason" in tool_input:
            cmd += f" {tool_input['reason']}"
        return await manager.send_command(server_id, "execute", {"command": cmd})
    elif tool_name == "op_player":
        return await manager.send_command(
            server_id, "execute", {"command": f"/op {tool_input['player']}"}
        )
    elif tool_name == "deop_player":
        return await manager.send_command(
            server_id, "execute", {"command": f"/deop {tool_input['player']}"}
        )
    elif tool_name == "get_status":
        return {"success": True, "output": str(current_status)}
    elif tool_name == "restart_server":
        return await manager.send_command(server_id, "restart", {})
    elif tool_name == "broadcast":
        return await manager.send_command(
            server_id, "execute", {"command": f"/say {tool_input['message']}"}
        )
    return {"success": False, "output": f"未知工具: {tool_name}"}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: dict = Depends(verify_token)):
    admin_id = user.get("sub", "admin")
    await require_server_access(admin_id, request.server_id, min_role="admin")

    if not await manager.is_online(request.server_id):
        raise HTTPException(status_code=503, detail="服务器未连接")

    current_status = await manager.get_status(request.server_id)
    status_data = current_status.get("data") if current_status else None

    # 记录会话活跃时间
    try:
        await memory_service.update_session_active(admin_id, request.server_id)
    except Exception as e:
        logger.warning(f"记录会话活跃时间失败: {e}")

    try:
        ai_response = await ai_agent.process_message(
            request.message,
            request.server_id,
            status_data,
            query_only=request.query_only,
            model_tier=request.model_tier,
            admin_id=admin_id,
        )
    except Exception as e:
        logger.error(f"AI processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI处理失败: {str(e)}")

    # 仅查询模式下跳过工具执行
    if request.query_only:
        return ChatResponse(
            message=ai_response.get("text", ""),
            command_executed=None,
            timestamp=datetime.now()
        )

    tool_calls = ai_response.get("tool_calls", [])
    if not tool_calls:
        return ChatResponse(
            message=ai_response.get("text", ""),
            command_executed=None,
            timestamp=datetime.now()
        )

    # ======== 命令审核流程 ========
    # 对所有工具调用逐个审核
    executed_commands = []
    last_review_info = None

    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_input = tool_call["input"]
        command = _extract_command_from_tool_call(tool_name, tool_input)

        # 审核
        review_result = await command_reviewer.review(
            command=command,
            tool_name=tool_name,
            user_message=request.message,
            server_status=status_data or {},
            user_id=admin_id,
            server_id=request.server_id,
        )

        if review_result.decision == ReviewDecision.APPROVED:
            # 放行 → 执行
            last_review_info = ReviewInfo(
                status="approved",
                risk_level=review_result.risk_level.value,
                reviewed_by=review_result.reviewed_by,
                reason=review_result.reason,
            )
            try:
                result = await _execute_tool(
                    request.server_id, tool_name, tool_input, current_status
                )
                executed_commands.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "result": result,
                })
                ai_agent.add_tool_result(
                    request.server_id, tool_call["id"], result.get("output", "")
                )
            except Exception as e:
                logger.error(f"Tool execution failed for {tool_name}: {e}")
                error_result = {"success": False, "output": f"执行失败: {str(e)}"}
                executed_commands.append({
                    "tool": tool_name, "input": tool_input, "result": error_result,
                })
                ai_agent.add_tool_result(
                    request.server_id, tool_call["id"], error_result["output"]
                )

        elif review_result.decision == ReviewDecision.REJECTED:
            # AI审核拒绝 → 不执行，返回拒绝原因
            reject_msg = f"操作被安全审核拦截：{review_result.reason}"
            if review_result.suggested_alternative:
                reject_msg += f"\n建议命令：{review_result.suggested_alternative}"
            last_review_info = ReviewInfo(
                status="rejected",
                risk_level=review_result.risk_level.value,
                reviewed_by=review_result.reviewed_by,
                reason=review_result.reason,
                suggestion=review_result.suggested_alternative,
            )
            ai_agent.add_tool_result(
                request.server_id, tool_call["id"], f"审核拒绝: {review_result.reason}"
            )
            return ChatResponse(
                message=reject_msg,
                command_executed=None,
                review=last_review_info,
                timestamp=datetime.now(),
            )

        elif review_result.decision == ReviewDecision.PENDING:
            # 高危 → 暂存到Redis，等待客户端确认
            pending_id = await command_reviewer.store_pending_command(
                user_id=admin_id,
                server_id=request.server_id,
                command=command,
                tool_call=tool_call,
                review_result=review_result,
            )
            pending_review = ReviewInfo(
                status="pending_confirmation",
                risk_level=review_result.risk_level.value,
                reviewed_by=review_result.reviewed_by,
                reason=review_result.reason,
                pending_id=pending_id,
                command=command,
                expires_in=settings.review_confirm_timeout,
            )
            ai_agent.add_tool_result(
                request.server_id, tool_call["id"], f"等待人工确认: {review_result.reason}"
            )
            return ChatResponse(
                message="这是一个高风险操作，需要你确认后才会执行：",
                command_executed=None,
                review=pending_review,
                timestamp=datetime.now(),
            )

    return ChatResponse(
        message=ai_response.get("text", ""),
        command_executed=executed_commands[0] if executed_commands else None,
        review=last_review_info,
        timestamp=datetime.now()
    )


# ======== 人工确认/拒绝端点 ========

@router.post("/chat/confirm/{pending_id}")
async def confirm_pending_command(
    pending_id: str,
    action: Literal["approve", "reject"] = Query(...),
    user: dict = Depends(verify_token),
):
    """用户确认或拒绝高危命令"""
    admin_id = user.get("sub", "admin")

    pending = await command_reviewer.get_pending_command(pending_id)
    if not pending:
        raise HTTPException(404, "确认请求已过期或不存在")

    if pending["user_id"] != admin_id:
        raise HTTPException(403, "无权操作")

    server_id = pending["server_id"]
    command = pending["command"]
    tool_call = pending["tool_call"]

    if action == "approve":
        # 确认 → 执行命令
        current_status = await manager.get_status(server_id)
        try:
            result = await _execute_tool(
                server_id, tool_call["name"], tool_call["input"], current_status
            )
            ai_agent.add_tool_result(
                server_id, tool_call["id"], result.get("output", "")
            )
        except Exception as e:
            result = {"success": False, "output": f"执行失败: {str(e)}"}

        await command_reviewer.delete_pending_command(pending_id)
        return {
            "success": True,
            "message": f"已执行: {command}",
            "output": result.get("output", ""),
            "command": command,
        }
    else:
        # 拒绝 → 取消
        ai_agent.add_tool_result(
            server_id, tool_call["id"], "用户取消了此操作"
        )
        await command_reviewer.delete_pending_command(pending_id)
        return {
            "success": True,
            "message": "已取消执行",
            "command": command,
        }


@router.get("/status/{server_id}", response_model=ServerStatus)
async def get_server_status(server_id: str, user: dict = Depends(verify_token)):
    username = user.get("sub")
    await require_server_access(username, server_id, min_role="admin")

    status = await manager.get_status(server_id)
    if not status:
        raise HTTPException(status_code=404, detail="服务器不存在")

    data = status.get("data", {})
    return ServerStatus(
        server_id=server_id,
        tps=data.get("tps", 0.0),
        players=data.get("players", []),
        memory_used_mb=data.get("memory_used_mb", 0),
        memory_max_mb=data.get("memory_max_mb", 0),
        recent_errors=data.get("recent_errors", []),
        last_update=status["last_update"],
        online=status["online"]
    )
