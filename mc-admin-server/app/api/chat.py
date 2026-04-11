from fastapi import APIRouter, Depends, HTTPException
from app.models.schemas import ChatRequest, ChatResponse, ServerStatus
from app.core.auth import verify_token
from app.services.ai_agent import ai_agent
from app.websocket.manager import manager
from datetime import datetime

router = APIRouter(prefix="/api/v1", tags=["chat"])

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: dict = Depends(verify_token)):
    if not manager.is_online(request.server_id):
        raise HTTPException(status_code=503, detail="服务器未连接")

    current_status = manager.get_status(request.server_id)

    ai_response = await ai_agent.process_message(
        request.message,
        request.server_id,
        current_status.get("data") if current_status else None
    )

    executed_commands = []
    for tool_call in ai_response.get("tool_calls", []):
        tool_name = tool_call["name"]
        tool_input = tool_call["input"]

        if tool_name == "execute_command":
            result = await manager.send_command(
                request.server_id,
                "execute",
                {"command": tool_input["command"]}
            )
        elif tool_name == "kick_player":
            cmd = f"/kick {tool_input['player']}"
            if "reason" in tool_input:
                cmd += f" {tool_input['reason']}"
            result = await manager.send_command(
                request.server_id,
                "execute",
                {"command": cmd}
            )
        elif tool_name == "op_player":
            result = await manager.send_command(
                request.server_id,
                "execute",
                {"command": f"/op {tool_input['player']}"}
            )
        elif tool_name == "deop_player":
            result = await manager.send_command(
                request.server_id,
                "execute",
                {"command": f"/deop {tool_input['player']}"}
            )
        elif tool_name == "get_status":
            result = {"success": True, "output": str(current_status)}
        elif tool_name == "restart_server":
            result = await manager.send_command(
                request.server_id,
                "restart",
                {}
            )
        elif tool_name == "broadcast":
            result = await manager.send_command(
                request.server_id,
                "execute",
                {"command": f"/say {tool_input['message']}"}
            )
        else:
            result = {"success": False, "output": f"未知工具: {tool_name}"}

        executed_commands.append({
            "tool": tool_name,
            "input": tool_input,
            "result": result
        })

        ai_agent.add_tool_result(
            request.server_id,
            tool_call["id"],
            result.get("output", "")
        )

    return ChatResponse(
        message=ai_response.get("text", ""),
        command_executed=executed_commands[0] if executed_commands else None,
        timestamp=datetime.now()
    )

@router.get("/status/{server_id}", response_model=ServerStatus)
async def get_server_status(server_id: str, user: dict = Depends(verify_token)):
    status = manager.get_status(server_id)
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
