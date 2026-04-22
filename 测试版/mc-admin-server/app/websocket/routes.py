from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from typing import Optional
from app.websocket.manager import manager
from app.websocket.chat_manager import chat_manager
from app.services.ai_agent import ai_agent
from app.services.memory import memory_service
from app.services.command_reviewer import command_reviewer
from app.services.spark_archive import capture_execute_command
from app.models.review import ReviewDecision
from app.models.schemas import ReviewInfo
from app.core.auth import decode_token
from app.core.permissions import require_server_access
from config.settings import settings
import json
import re
import logging
import copy

logger = logging.getLogger(__name__)

router = APIRouter()

# server_id 格式：字母、数字、下划线、连字符，1-64字符
_VALID_SERVER_ID = re.compile(r'^[a-zA-Z0-9_\-]{1,64}$')

# WebSocket 单条消息最大大小（100KB）
_MAX_WS_MESSAGE_SIZE = 100 * 1024

# 合法的消息类型
_VALID_MESSAGE_TYPES = {"status", "result", "ai_chat_request", "confirm_required", "ping"}


@router.websocket("/ws/mod")
async def mod_websocket(
    websocket: WebSocket,
    server_id: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
):
    # 优先从Header读取认证信息（更安全），兼容旧版query param方式
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
    if not server_id:
        server_id = websocket.headers.get("x-server-id", "").strip()

    if not server_id or not token:
        await websocket.close(code=1008, reason="Missing credentials")
        return

    # 校验 server_id 格式
    if not _VALID_SERVER_ID.match(server_id):
        await websocket.close(code=1008, reason="Invalid server_id format")
        return

    connected = await manager.connect(websocket, server_id, token)
    if not connected:
        return

    try:
        while True:
            data = await websocket.receive_text()

            # 消息大小限制：直接关闭连接，避免被恶意客户端持续发送大包耗资源
            if len(data) > _MAX_WS_MESSAGE_SIZE:
                logger.warning(f"WebSocket消息过大 ({len(data)} bytes) from {server_id}，关闭连接")
                await websocket.close(code=1009, reason="Message too big")
                await manager.disconnect(server_id)
                return

            # JSON解析
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"WebSocket收到无效JSON from {server_id}")
                continue

            # 消息格式校验
            if not isinstance(message, dict) or "type" not in message:
                logger.warning(f"WebSocket消息缺少type字段 from {server_id}")
                continue

            # 消息类型白名单
            if message.get("type") not in _VALID_MESSAGE_TYPES:
                logger.warning(f"WebSocket收到未知消息类型 '{message.get('type')}' from {server_id}")
                continue

            await manager.handle_message(server_id, message)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {server_id}")
        await manager.disconnect(server_id)
    except Exception as e:
        logger.error(f"WebSocket error for {server_id}: {e}", exc_info=True)
        await manager.disconnect(server_id)


# MC玩家名仅允许字母、数字、下划线，长度1-16
_VALID_MC_NAME = re.compile(r'^[a-zA-Z0-9_]{1,16}$')


def _validate_player_name(name: str) -> str:
    """验证MC玩家名，防止命令注入"""
    if not _VALID_MC_NAME.match(name):
        raise ValueError(f"无效的玩家名: {name}")
    return name


def _tool_to_mc_command(tool_name: str, tool_input: dict) -> str | None:
    """将工具调用转换为MC命令字符串，非命令类工具返回None"""
    if tool_name == "execute_command":
        return tool_input.get("command", "")
    if tool_name == "kick_player":
        player = _validate_player_name(tool_input['player'])
        cmd = f"/kick {player}"
        if "reason" in tool_input:
            reason = re.sub(r'[\r\n\x00-\x1f]', '', tool_input['reason'])[:100]
            cmd += f" {reason}"
        return cmd
    if tool_name == "op_player":
        return f"/op {_validate_player_name(tool_input['player'])}"
    if tool_name == "deop_player":
        return f"/deop {_validate_player_name(tool_input['player'])}"
    if tool_name == "broadcast":
        message = re.sub(r'[\r\n\x00-\x1f]', '', tool_input['message'])[:256]
        return f"/say {message}"
    return None


def _extract_command_from_tool_call(tool_name: str, tool_input: dict) -> str:
    """从工具调用中提取命令字符串（用于审核）"""
    return _tool_to_mc_command(tool_name, tool_input) or tool_name


async def _execute_tool(server_id: str, tool_name: str, tool_input: dict, current_status: dict) -> dict:
    """执行单个工具调用"""
    if tool_name == "get_status":
        return {"success": True, "output": str(current_status)}
    if tool_name == "restart_server":
        return await manager.send_command(server_id, "restart", {})
    if tool_name == "read_log":
        payload: dict = {}
        lines = tool_input.get("lines")
        if isinstance(lines, int):
            payload["lines"] = lines
        keyword = tool_input.get("keyword")
        if isinstance(keyword, str) and keyword.strip():
            payload["keyword"] = keyword.strip()[:100]
        return await manager.send_command(server_id, "read_log", payload, timeout=15)
    mc_cmd = _tool_to_mc_command(tool_name, tool_input)
    if mc_cmd is not None:
        return await manager.send_command(server_id, "execute", {"command": mc_cmd})
    return {"success": False, "output": f"未知工具: {tool_name}"}


@router.websocket("/ws/chat")
async def chat_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    server_id: Optional[str] = Query(None),
):
    """
    客户端聊天 WebSocket 端点（流式 AI 对话）

    客户端发送：
    {
        "type": "chat",
        "message": "用户消息",
        "query_only": false,  // 可选
        "model_tier": "flash"  // 可选: flash/standard/pro
    }

    服务器推送：
    {"type": "text_delta", "text": "..."}  // 文本增量
    {"type": "tool_call", "id": "...", "name": "...", "input": {...}}  // 工具调用
    {"type": "tool_result", "id": "...", "output": "..."}  // 工具执行结果
    {"type": "done", "model_used": "...", "degraded": false}  // 完成
    {"type": "error", "error": "..."}  // 错误
    {"type": "review_pending", "review": {...}}  // 需要人工确认
    """
    # 从 Header 或 Query 获取认证信息
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
    if not server_id:
        server_id = websocket.headers.get("x-server-id", "").strip()

    if not token or not server_id:
        await websocket.close(code=1008, reason="Missing credentials")
        return

    # 验证 token
    try:
        payload = decode_token(token)
        admin_id = payload.get("sub", "admin")
    except Exception as e:
        logger.warning(f"聊天WS鉴权失败: {e}")
        await websocket.close(code=1008, reason="Invalid token")
        return

    # 验证服务器访问权限
    try:
        await require_server_access(admin_id, server_id, min_role="admin")
    except HTTPException:
        await websocket.close(code=1008, reason="No server access")
        return

    # 建立连接
    await chat_manager.connect(websocket, admin_id, server_id)

    try:
        while True:
            data = await websocket.receive_text()

            # 消息大小限制
            if len(data) > _MAX_WS_MESSAGE_SIZE:
                await chat_manager.send_message(admin_id, server_id, {
                    "type": "error",
                    "error": "消息过大"
                })
                continue

            # JSON 解析
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await chat_manager.send_message(admin_id, server_id, {
                    "type": "error",
                    "error": "无效的JSON"
                })
                continue

            # 消息类型检查
            if not isinstance(message, dict) or message.get("type") != "chat":
                await chat_manager.send_message(admin_id, server_id, {
                    "type": "error",
                    "error": "无效的消息类型"
                })
                continue

            user_message = message.get("message", "").strip()
            if not user_message:
                await chat_manager.send_message(admin_id, server_id, {
                    "type": "error",
                    "error": "消息不能为空"
                })
                continue

            query_only = message.get("query_only", False)
            model_tier = message.get("model_tier")

            # 检查服务器是否在线（非仅查询模式需要）
            if not query_only:
                server_online = await manager.is_online(server_id)
                if not server_online:
                    await chat_manager.send_message(admin_id, server_id, {
                        "type": "error",
                        "error": "服务器未连接，无法执行指令。可切换到仅查询模式咨询AI"
                    })
                    continue

            # 获取服务器状态
            current_status = await manager.get_status(server_id)
            status_data = current_status.get("data") if current_status else None

            # 记录会话活跃时间
            try:
                await memory_service.update_session_active(admin_id, server_id)
            except Exception as e:
                logger.warning(f"记录会话活跃时间失败: {e}")

            # 流式处理 AI 响应
            try:
                async for event in ai_agent.process_message_stream(
                    user_message,
                    server_id,
                    status_data,
                    query_only=query_only,
                    model_tier=model_tier,
                    admin_id=admin_id,
                ):
                    event_type = event.get("type")

                    if event_type == "text_delta":
                        # 文本增量，直接转发
                        await chat_manager.send_message(admin_id, server_id, event)

                    elif event_type == "tool_call":
                        # 工具调用，需要审核
                        tool_id = event["id"]
                        tool_name = event["name"]
                        tool_input = event["input"]

                        # 先发送工具调用通知
                        await chat_manager.send_message(admin_id, server_id, event)

                        if query_only:
                            # 仅查询模式不执行工具
                            continue

                        # 审核命令
                        command = _extract_command_from_tool_call(tool_name, tool_input)
                        review_result = await command_reviewer.review(
                            command=command,
                            tool_name=tool_name,
                            user_message=user_message,
                            server_status=status_data or {},
                            user_id=admin_id,
                            server_id=server_id,
                        )

                        if review_result.decision == ReviewDecision.APPROVED:
                            # 放行 → 执行
                            try:
                                result = await _execute_tool(
                                    server_id, tool_name, tool_input, current_status
                                )
                                # 发送工具执行结果
                                await chat_manager.send_message(admin_id, server_id, {
                                    "type": "tool_result",
                                    "id": tool_id,
                                    "output": result.get("output", ""),
                                    "success": result.get("success", False),
                                })
                                # 添加到 AI 历史
                                ai_agent.add_tool_result(
                                    admin_id, server_id, tool_id, result.get("output", "")
                                )
                                # 档案馆：识别 /spark profiler start|stop 并落库
                                if tool_name == "execute_command":
                                    await capture_execute_command(
                                        admin_id, server_id,
                                        tool_input.get("command", ""), result,
                                    )
                            except Exception as e:
                                logger.error(f"工具执行失败 {tool_name}: {e}")
                                error_output = f"执行失败: {str(e)}"
                                await chat_manager.send_message(admin_id, server_id, {
                                    "type": "tool_result",
                                    "id": tool_id,
                                    "output": error_output,
                                    "success": False,
                                })
                                ai_agent.add_tool_result(admin_id, server_id, tool_id, error_output)

                        elif review_result.decision == ReviewDecision.REJECTED:
                            # 拒绝
                            reject_msg = f"操作被安全审核拦截：{review_result.reason}"
                            await chat_manager.send_message(admin_id, server_id, {
                                "type": "tool_result",
                                "id": tool_id,
                                "output": reject_msg,
                                "success": False,
                                "rejected": True,
                            })
                            ai_agent.add_tool_result(
                                admin_id, server_id, tool_id, f"审核拒绝: {review_result.reason}"
                            )

                        elif review_result.decision == ReviewDecision.PENDING:
                            # 高危 → 需要人工确认
                            try:
                                pending_id = await command_reviewer.store_pending_command(
                                    user_id=admin_id,
                                    server_id=server_id,
                                    command=command,
                                    tool_call={"id": tool_id, "name": tool_name, "input": tool_input},
                                    review_result=review_result,
                                )
                                await chat_manager.send_message(admin_id, server_id, {
                                    "type": "review_pending",
                                    "review": {
                                        "status": "pending_confirmation",
                                        "risk_level": review_result.risk_level.value,
                                        "reviewed_by": review_result.reviewed_by,
                                        "reason": review_result.reason,
                                        "pending_id": pending_id,
                                        "command": command,
                                        "expires_in": settings.review_confirm_timeout,
                                    }
                                })
                                ai_agent.add_tool_result(
                                    admin_id, server_id, tool_id, f"等待人工确认: {review_result.reason}"
                                )
                            except Exception as e:
                                logger.error(f"暂存待确认命令失败: {e}")
                                await chat_manager.send_message(admin_id, server_id, {
                                    "type": "error",
                                    "error": "审核服务暂不可用，操作已拦截"
                                })

                    elif event_type == "done":
                        # 完成，转发元数据
                        await chat_manager.send_message(admin_id, server_id, event)

                    elif event_type == "error":
                        # 错误，转发
                        await chat_manager.send_message(admin_id, server_id, event)

            except Exception as e:
                logger.error(f"流式处理出错: {e}", exc_info=True)
                await chat_manager.send_message(admin_id, server_id, {
                    "type": "error",
                    "error": f"AI处理失败: {str(e)}"
                })

    except WebSocketDisconnect:
        logger.info(f"聊天WS断开: {admin_id}@{server_id}")
        await chat_manager.disconnect(admin_id, server_id)
    except Exception as e:
        logger.error(f"聊天WS错误: {e}", exc_info=True)
        await chat_manager.disconnect(admin_id, server_id)
