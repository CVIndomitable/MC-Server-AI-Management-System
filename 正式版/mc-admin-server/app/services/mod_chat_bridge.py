"""
游戏内玩家聊天（模组拦截 → WebSocket ai_chat_request）的处理管线。

与 /api/v1/chat 的区别：
- 请求来自受信的模组（已通过 WS token 鉴权），使用合成 admin_id = "mod:<uuid>"
- 不走 DB 用户权限检查（玩家能在服上就有权限）
- 审核 PENDING / REJECTED 不走 Redis 暂存，直接告诉玩家到管理后台处理
"""
import json
import logging
from datetime import datetime

from app.websocket.manager import manager
from app.services.ai_agent import ai_agent
from app.services.command_reviewer import command_reviewer
from app.models.review import ReviewDecision

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LEN = 4000


def _safe(s, default=""):
    return s if isinstance(s, str) and s else default


async def handle_ai_chat_request(server_id: str, message: dict):
    # 延迟导入，避免循环依赖（chat.py 也 import manager）
    from app.api.chat import _execute_tool, _extract_command_from_tool_call

    request_id = _safe(message.get("request_id"))
    player_id = _safe(message.get("player_id"))
    player_name = _safe(message.get("player_name"), "player")
    user_message = _safe(message.get("message"))
    model_tier = _safe(message.get("model_tier"), "standard")
    query_only = bool(message.get("query_only"))

    if not request_id or not user_message:
        logger.warning(f"ai_chat_request from {server_id} missing required fields")
        return

    if len(user_message) > _MAX_MESSAGE_LEN:
        user_message = user_message[:_MAX_MESSAGE_LEN]

    admin_id = f"mod:{player_id or player_name}"

    try:
        current_status = await manager.get_status(server_id)
    except Exception as e:
        logger.warning(f"获取状态失败: {e}")
        current_status = None
    status_data = current_status.get("data") if current_status else None

    # 1) AI 生成
    try:
        ai_response = await ai_agent.process_message(
            user_message,
            server_id,
            status_data,
            query_only=query_only,
            model_tier=model_tier,
            admin_id=admin_id,
        )
    except Exception as e:
        logger.error(f"mod_chat AI 处理失败: {e}")
        await _reply(server_id, request_id, error="AI 处理失败，请稍后重试")
        return

    text = _safe(ai_response.get("text"))

    # 2) 仅查询模式 或 无工具调用 → 直接回话
    tool_calls = ai_response.get("tool_calls", []) or []
    if query_only or not tool_calls:
        await _reply(server_id, request_id, text=text or "（AI 未返回文本）")
        return

    # 3) 工具调用：逐条审核执行
    executed_any = False
    for tc in tool_calls:
        tn = tc.get("name", "")
        ti = tc.get("input", {}) or {}
        tc_id = tc.get("id", "")
        command = _extract_command_from_tool_call(tn, ti)

        try:
            review = await command_reviewer.review(
                command=command,
                tool_name=tn,
                user_message=user_message,
                server_status=status_data or {},
                user_id=admin_id,
                server_id=server_id,
            )
        except Exception as e:
            logger.error(f"mod_chat 审核异常: {e}")
            ai_agent.add_tool_result(admin_id, server_id, tc_id, f"审核异常: {e}")
            await _reply(server_id, request_id, error="审核服务异常，操作未执行")
            return

        if review.decision == ReviewDecision.APPROVED:
            try:
                result = await _execute_tool(server_id, tn, ti, current_status)
                ai_agent.add_tool_result(admin_id, server_id, tc_id, result.get("output", ""))
                executed_any = True
                if result.get("success"):
                    try:
                        from app.api.chat import _maybe_register_async_caller
                        await _maybe_register_async_caller(
                            admin_id=admin_id,
                            server_id=server_id,
                            tool_name=tn,
                            tool_input=ti,
                            command=command,
                        )
                    except Exception as e:
                        logger.warning(f"mod_chat 登记异步调用者失败: {e}")
            except Exception as e:
                logger.error(f"mod_chat 工具执行失败: {e}")
                ai_agent.add_tool_result(admin_id, server_id, tc_id, f"执行失败: {e}")
        elif review.decision == ReviewDecision.REJECTED:
            reject = f"操作被拦截：{review.reason}"
            if review.suggested_alternative:
                reject += f"\n建议：{review.suggested_alternative}"
            ai_agent.add_tool_result(admin_id, server_id, tc_id, f"审核拒绝: {review.reason}")
            await _reply(server_id, request_id, text=reject)
            return
        else:  # PENDING / 其他
            hint = f"高风险操作需要人工确认，请到管理后台处理：{command}"
            ai_agent.add_tool_result(admin_id, server_id, tc_id, "待人工确认（游戏内不支持）")
            await _reply(server_id, request_id, text=hint)
            return

    # 4) 让 AI 基于工具结果总结
    final_text = text or "已执行"
    if executed_any:
        try:
            summary = await ai_agent.continue_after_tools(
                admin_id=admin_id,
                server_id=server_id,
                user_message=user_message,
                query_only=query_only,
                model_tier=model_tier,
            )
            final_text = _safe(summary.get("text")) or final_text
        except Exception as e:
            logger.warning(f"continue_after_tools 失败: {e}")

    await _reply(server_id, request_id, text=final_text)


async def _reply(server_id: str, request_id: str, *, text: str = None, error: str = None):
    msg = {
        "type": "ai_chat_response",
        "request_id": request_id,
        "timestamp": datetime.now().isoformat(),
    }
    if text is not None:
        msg["message"] = text
    if error is not None:
        msg["error"] = error
    await manager.send_raw(server_id, msg)
