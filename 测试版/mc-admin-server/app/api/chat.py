from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from app.models.schemas import ChatRequest, ChatResponse, ServerStatus, ReviewInfo
from app.models.review import ReviewDecision
from app.core.auth import verify_token
from app.core.permissions import require_server_access
from app.core.database import user_db
from app.services.ai_agent import ai_agent
from app.services.memory import memory_service
from app.services.command_reviewer import command_reviewer
from app.services.spark_archive import capture_execute_command
from app.websocket.manager import manager
from app.utils.rate_limiter import rate_limiter
from config.settings import settings
from datetime import datetime
from typing import Literal, Optional
import httpx
import json
import re
import logging

_MAX_MESSAGE_LEN = 4000

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


async def _check_chat_rate(user_id: str):
    """检查聊天API速率限制（基于Redis的分布式限流）"""
    await rate_limiter.check_rate(
        f"chat:user:{user_id}",
        settings.chat_rate_limit,
        settings.chat_rate_window
    )

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
            # 原因字段去除换行和控制字符
            reason = re.sub(r'[\r\n\x00-\x1f]', '', tool_input['reason'])[:100]
            cmd += f" {reason}"
        return cmd
    if tool_name == "op_player":
        return f"/op {_validate_player_name(tool_input['player'])}"
    if tool_name == "deop_player":
        return f"/deop {_validate_player_name(tool_input['player'])}"
    if tool_name == "broadcast":
        # 广播消息去除控制字符，限制长度
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
        # 读日志要扫全文件，给个更宽裕的超时
        return await manager.send_command(server_id, "read_log", payload, timeout=15)
    if tool_name == "read_url":
        url = tool_input.get("url", "").strip()
        if not url or not url.startswith(("http://", "https://")):
            return {"success": False, "output": "无效URL"}
        if len(url) > 2048:
            return {"success": False, "output": "URL过长"}
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                # Spark 报告页面是 JS 动态渲染，原始 URL 只拿到空 SPA 壳。
                # 检测到 spark.lucko.me 时，改用其 JSON data API。
                fetch_url = url
                spark_match = re.match(r"https?://spark\.lucko\.me/([A-Za-z0-9_\-]+)$", url)
                if spark_match:
                    fetch_url = f"https://spark.lucko.me/data/{spark_match.group(1)}"
                    logger.info(f"read_url → spark data API: {fetch_url}")
                    resp = await client.get(fetch_url, headers={
                        "User-Agent": "MCAdmin-AI/1.0",
                        "Accept": "application/json",
                    })
                else:
                    resp = await client.get(url, headers={"User-Agent": "MCAdmin-AI/1.0"})
                resp.raise_for_status()
                text = resp.text[:100_000]  # 限制100KB
                return {"success": True, "output": text}
        except httpx.TimeoutException:
            return {"success": False, "output": "请求超时"}
        except httpx.HTTPStatusError as e:
            return {"success": False, "output": f"HTTP错误: {e.response.status_code}"}
        except Exception as e:
            return {"success": False, "output": f"读取失败: {str(e)}"}

    mc_cmd = _tool_to_mc_command(tool_name, tool_input)
    if mc_cmd is not None:
        return await manager.send_command(server_id, "execute", {"command": mc_cmd})
    return {"success": False, "output": f"未知工具: {tool_name}"}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: dict = Depends(verify_token)):
    admin_id = user.get("sub", "admin")
    await _check_chat_rate(admin_id)
    await require_server_access(admin_id, request.server_id, min_role="admin")

    server_online = await manager.is_online(request.server_id)

    # 非仅��询模式下，模组必须在线才能执行指令
    if not server_online and not request.query_only:
        raise HTTPException(status_code=503, detail="服务器未连接，无法执行指令。可切换到仅查询模��咨询AI")

    current_status = await manager.get_status(request.server_id)
    status_data = current_status.get("data") if current_status else None

    # 记录会话活跃时间
    try:
        await memory_service.update_session_active(admin_id, request.server_id)
    except Exception as e:
        logger.warning(f"记录会话活跃时间失败: {e}")

    # 记录用户消息
    _log_chat(admin_id, request.server_id, "user", content=request.message)

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
        raise HTTPException(status_code=500, detail="AI处理失败，请稍后重试")

    degraded = bool(ai_response.get("degraded"))
    degraded_message = (
        f"主 LLM 供应商不可用，已切换到备用供应商「{ai_response.get('provider_used')}」"
        if degraded else None
    )

    # 仅查询模式下跳过工具执行
    if request.query_only:
        return ChatResponse(
            message=ai_response.get("text", ""),
            command_executed=None,
            timestamp=datetime.now(),
            degraded=degraded,
            degraded_message=degraded_message,
        )

    tool_calls = ai_response.get("tool_calls", [])
    if not tool_calls:
        return ChatResponse(
            message=ai_response.get("text", ""),
            command_executed=None,
            timestamp=datetime.now(),
            degraded=degraded,
            degraded_message=degraded_message,
        )

    # 缓存命中标志（走同一审核流程，只是跳过了 LLM 调用本身）
    cache_hit = bool(ai_response.get("cache_hit"))

    # 记录 AI 响应
    _log_chat(admin_id, request.server_id, "assistant",
              content=ai_response.get("text") if not tool_calls else None,
              tool_calls=tool_calls if tool_calls else None,
              model_used=ai_response.get("model_used"),
              provider_used=ai_response.get("provider_used"),
              cache_hit=cache_hit)

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
                    admin_id, request.server_id, tool_call["id"], result.get("output", "")
                )
                # 档案馆：识别 /spark profiler start|stop 并落库（内部已吞异常）
                if tool_name == "execute_command":
                    await capture_execute_command(
                        admin_id, request.server_id,
                        tool_input.get("command", ""), result,
                    )
            except Exception as e:
                logger.error(f"Tool execution failed for {tool_name}: {e}")
                error_result = {"success": False, "output": f"执行失败: {str(e)}"}
                executed_commands.append({
                    "tool": tool_name, "input": tool_input, "result": error_result,
                })
                ai_agent.add_tool_result(
                    admin_id, request.server_id, tool_call["id"], error_result["output"]
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
                admin_id, request.server_id, tool_call["id"], f"审核拒绝: {review_result.reason}"
            )
            return ChatResponse(
                message=reject_msg,
                command_executed=None,
                review=last_review_info,
                timestamp=datetime.now(),
                degraded=degraded,
                degraded_message=degraded_message,
            )

        elif review_result.decision == ReviewDecision.PENDING:
            # 高危 → 暂存到Redis，等待客户端确认
            try:
                pending_id = await command_reviewer.store_pending_command(
                    user_id=admin_id,
                    server_id=request.server_id,
                    command=command,
                    tool_call=tool_call,
                    review_result=review_result,
                )
            except Exception as e:
                logger.error(f"暂存待确认命令失败: {e}")
                ai_agent.add_tool_result(
                    admin_id, request.server_id, tool_call["id"],
                    f"审核服务异常，操作未执行: {review_result.reason}"
                )
                return ChatResponse(
                    message=f"高风险操作需要确认，但审核服务暂不可用，请稍后重试。\n原因：{review_result.reason}",
                    command_executed=None,
                    review=ReviewInfo(
                        status="rejected",
                        risk_level=review_result.risk_level.value,
                        reviewed_by=review_result.reviewed_by,
                        reason="审核服务不可用，操作已拦截",
                    ),
                    timestamp=datetime.now(),
                    degraded=degraded,
                    degraded_message=degraded_message,
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
                admin_id, request.server_id, tool_call["id"], f"等待人工确认: {review_result.reason}"
            )
            return ChatResponse(
                message="这是一个高风险操作，需要你确认后才会执行：",
                command_executed=None,
                review=pending_review,
                timestamp=datetime.now(),
                degraded=degraded,
                degraded_message=degraded_message,
            )

    if executed_commands:
        # 记录工具执行结果
        _log_chat(admin_id, request.server_id, "tool_result",
                  tool_results=[{"tool": c["tool"], "input": c["input"]} for c in executed_commands])
        # 缓存命中时跳过二次 LLM 调用，直接复用 cache 中的文本；只有首次走 LLM 时才 summary
        if cache_hit:
            final_text = ai_response.get("text", "") or "（已执行，但AI未返回描述）"
        else:
            summary = await ai_agent.continue_after_tools(
                admin_id=admin_id,
                server_id=request.server_id,
                user_message=request.message,
                query_only=request.query_only,
                model_tier=request.model_tier,
            )
            final_text = summary.get("text") or ai_response.get("text", "") or "（已执行，但AI未返回描述）"
            degraded = degraded or bool(summary.get("degraded"))
            # 记录 AI 总结
            _log_chat(admin_id, request.server_id, "assistant_summary",
                      content=final_text,
                      model_used=ai_response.get("model_used"),
                      provider_used=summary.get("provider_used"))
    else:
        final_text = ai_response.get("text", "")

    return ChatResponse(
        message=final_text,
        command_executed=executed_commands[0] if executed_commands else None,
        review=last_review_info,
        timestamp=datetime.now(),
        degraded=degraded,
        degraded_message=degraded_message,
    )


# ---- SSE 流式聊天端点 ----

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _tool_label(tool_name: str, tool_input: dict) -> str:
    """生成工具执行的可读描述，用于客户端状态显示。"""
    labels = {
        "execute_command": f"执行指令: {tool_input.get('command', '?')[:60]}",
        "kick_player": f"踢出玩家: {tool_input.get('player', '?')}",
        "op_player": f"给予OP: {tool_input.get('player', '?')}",
        "deop_player": f"移除OP: {tool_input.get('player', '?')}",
        "get_status": "获取服务器状态",
        "read_log": f"读取日志" + (f" (关键字: {tool_input.get('keyword')})" if tool_input.get('keyword') else ""),
        "read_url": f"读取网页: {tool_input.get('url', '?')[:80]}",
        "restart_server": "重启服务器",
        "broadcast": "发送全服公告",
    }
    return labels.get(tool_name, f"执行: {tool_name}")


def _log_chat(admin_id, server_id, role, content=None, tool_calls=None,
              tool_results=None, model_used=None, provider_used=None,
              error=None, cache_hit=False):
    """异步写入聊天日志，不阻塞主流程。"""
    import asyncio
    asyncio.create_task(
        user_db.log_chat(
            admin_id=admin_id, server_id=server_id, role=role,
            content=content,
            tool_calls_json=json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
            tool_results_json=json.dumps(tool_results, ensure_ascii=False) if tool_results else None,
            model_used=model_used, provider_used=provider_used,
            error=error, cache_hit=cache_hit,
        )
    )


@router.get("/chat/stream")
async def chat_stream(
    message: str = Query(..., min_length=1, max_length=_MAX_MESSAGE_LEN),
    server_id: str = Query(..., min_length=1),
    query_only: bool = Query(False),
    model_tier: Optional[str] = Query(None),
    user: dict = Depends(verify_token),
):
    """SSE 流式聊天，用于 iOS/Web 客户端。事件流：
    - text_delta:  {"text": "..."}
    - done:        {"degraded": bool, "model_used": "..."}
    - error:       {"error": "..."}
    """
    admin_id = user.get("sub", "admin")
    await _check_chat_rate(admin_id)
    await require_server_access(admin_id, server_id, min_role="admin")

    server_online = await manager.is_online(server_id)
    if not server_online and not query_only:
        raise HTTPException(status_code=503, detail="服务器未连接，无法执行指令。可切换到仅查询模式咨询AI")

    current_status = await manager.get_status(server_id)
    status_data = current_status.get("data") if current_status else None

    try:
        await memory_service.update_session_active(admin_id, server_id)
    except Exception as e:
        logger.warning(f"记录会话活跃时间失败: {e}")

    async def _event_stream():
        tool_calls = []
        used_provider = None
        degraded = False
        model_used = None

        # 记录用户消息
        _log_chat(admin_id, server_id, "user", content=message)

        try:
            async for event in ai_agent.process_message_stream(
                message, server_id, status_data,
                query_only=query_only,
                model_tier=model_tier,
                admin_id=admin_id,
            ):
                et = event.get("type")

                if et == "text_delta":
                    yield _sse("text_delta", {"text": event["text"]})

                elif et == "tool_call":
                    tool_calls.append(event)

                elif et == "done":
                    degraded = event.get("degraded", False)
                    model_used = event.get("model_used")
                    used_provider = event.get("provider_used")
                    # 记录 AI 响应（工具调用）
                    _log_chat(admin_id, server_id, "assistant",
                              tool_calls=tool_calls if tool_calls else None,
                              model_used=model_used,
                              provider_used=used_provider,
                              cache_hit=event.get("cache_hit", False))

                elif et == "error":
                    yield _sse("error", {"error": event["error"]})
                    return

            # ---- 工具执行 + 续写摘要 ----
            if tool_calls and not query_only:
                executed = []
                for tc in tool_calls:
                    tn = tc.get("name", "")
                    ti = tc.get("input", {}) or {}
                    tc_id = tc.get("id", "")
                    command = _extract_command_from_tool_call(tn, ti)

                    try:
                        review = await command_reviewer.review(
                            command=command, tool_name=tn,
                            user_message=message,
                            server_status=status_data or {},
                            user_id=admin_id, server_id=server_id,
                        )
                    except Exception as e:
                        logger.error(f"流式审核异常: {e}")
                        continue

                    if review.decision == ReviewDecision.APPROVED:
                        # 通知客户端正在执行工具
                        yield _sse("tool_start", {
                            "tool": tn,
                            "label": _tool_label(tn, ti),
                            "id": tc_id,
                        })
                        try:
                            result = await _execute_tool(server_id, tn, ti, current_status)
                            ai_agent.add_tool_result(admin_id, server_id, tc_id, result.get("output", ""))
                            executed.append(tc)
                            if tn == "execute_command":
                                await capture_execute_command(
                                    admin_id, server_id,
                                    ti.get("command", ""), result,
                                )
                            yield _sse("tool_end", {
                                "id": tc_id,
                                "success": result.get("success", False),
                            })
                        except Exception as e:
                            logger.error(f"流式工具执行失败: {e}")
                            ai_agent.add_tool_result(admin_id, server_id, tc_id, f"执行失败: {e}")
                            yield _sse("tool_end", {
                                "id": tc_id,
                                "success": False,
                                "error": str(e),
                            })
                    elif review.decision == ReviewDecision.REJECTED:
                        msg = f"操作被拦截：{review.reason}"
                        if review.suggested_alternative:
                            msg += f"\n建议：{review.suggested_alternative}"
                        ai_agent.add_tool_result(admin_id, server_id, tc_id, f"审核拒绝: {review.reason}")
                        yield _sse("text_delta", {"text": f"\n\n⚠️ {msg}"})
                        return
                    else:  # PENDING
                        ai_agent.add_tool_result(admin_id, server_id, tc_id, "待人工确认（流式暂不支持，请到后台确认）")
                        yield _sse("text_delta", {"text": f"\n\n🔒高风险操作需要确认：{command}"})
                        return

                if executed:
                    # 记录工具执行结果
                    _log_chat(admin_id, server_id, "tool_result",
                              tool_results=[{"tool": tc.get("name"), "input": tc.get("input")} for tc in executed])
                    summary = await ai_agent.continue_after_tools(
                        admin_id=admin_id, server_id=server_id,
                        user_message=message,
                        query_only=query_only, model_tier=model_tier,
                    )
                    s_text = summary.get("text", "")
                    if s_text:
                        yield _sse("text_delta", {"text": f"\n\n{s_text}"})
                    else:
                        yield _sse("text_delta", {"text": "\n\n（AI 未返回分析结果，请重试或换个问法）"})
                    # 记录 AI 总结
                    _log_chat(admin_id, server_id, "assistant_summary",
                              content=s_text or "(空)",
                              model_used=model_used,
                              provider_used=summary.get("provider_used"))

            yield _sse("done", {
                "degraded": degraded,
                "model_used": model_used,
                "provider_used": used_provider,
            })

        except Exception as e:
            logger.error(f"流式聊天失败: {e}", exc_info=True)
            yield _sse("error", {"error": "AI处理失败，请稍后重试"})

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ======== 清除对话历史 ========

@router.post("/chat/clear")
async def clear_conversation(
    server_id: str = Query(...),
    user: dict = Depends(verify_token),
):
    """清除当前用户+服务器的 AI 对话历史，开始新对话"""
    admin_id = user.get("sub", "admin")
    await require_server_access(admin_id, server_id, min_role="admin")
    ai_agent.clear_conversation(admin_id, server_id)
    return {"message": "对话历史已清除"}


# ======== 人工确认/拒绝端点 ========

@router.post("/chat/confirm/{pending_id}")
async def confirm_pending_command(
    pending_id: str,
    action: Literal["approve", "reject"] = Query(...),
    user: dict = Depends(verify_token),
):
    """用户确认或拒绝高危命令"""
    admin_id = user.get("sub", "admin")

    # 原子获取并删除，防止并发重复执行
    pending = await command_reviewer.get_and_delete_pending_command(pending_id)
    if not pending:
        raise HTTPException(404, "确认请求已过期或不存在")

    if pending["user_id"] != admin_id:
        # 非本人操作，回写数据让真正的用户可以操作
        await command_reviewer.store_pending_command_raw(pending_id, pending)
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
                admin_id, server_id, tool_call["id"], result.get("output", "")
            )
        except Exception as e:
            result = {"success": False, "output": f"执行失败: {str(e)}"}

        return {
            "success": True,
            "message": f"已执行: {command}",
            "output": result.get("output", ""),
            "command": command,
        }
    else:
        # 拒绝 → 取消
        ai_agent.add_tool_result(
            admin_id, server_id, tool_call["id"], "用户取消了此操作"
        )
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
        # 模组未连接时返回默认离线状态，而不是404
        return ServerStatus(
            server_id=server_id,
            tps=0.0,
            players=[],
            memory_used_mb=0,
            memory_max_mb=0,
            cpu_process=None,
            cpu_system=None,
            cpu_cores=None,
            recent_errors=[],
            last_update=None,
            online=False
        )

    data = status.get("data", {})
    return ServerStatus(
        server_id=server_id,
        tps=data.get("tps", 0.0),
        players=data.get("players", []),
        memory_used_mb=data.get("memory_used_mb", 0),
        memory_max_mb=data.get("memory_max_mb", 0),
        cpu_process=data.get("cpu_process"),
        cpu_system=data.get("cpu_system"),
        cpu_cores=data.get("cpu_cores"),
        recent_errors=data.get("recent_errors", []),
        last_update=status["last_update"],
        online=status["online"]
    )
