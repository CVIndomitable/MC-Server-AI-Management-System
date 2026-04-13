from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# WebSocket消息模型
class StatusReport(BaseModel):
    type: str = "status"
    server_id: str
    timestamp: int
    data: dict

class CommandRequest(BaseModel):
    type: str = "command"
    id: str
    action: str
    payload: dict

class CommandResult(BaseModel):
    type: str = "result"
    command_id: str
    success: bool
    output: str

# API请求/响应模型
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    server_id: str
    query_only: bool = False  # 仅查询模式：AI只建议不执行

class ChatResponse(BaseModel):
    message: str
    command_executed: Optional[dict] = None
    timestamp: datetime

class ServerStatus(BaseModel):
    server_id: str
    tps: float
    players: List[str]
    memory_used_mb: int
    memory_max_mb: int
    recent_errors: List[str]
    last_update: datetime
    online: bool

class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
