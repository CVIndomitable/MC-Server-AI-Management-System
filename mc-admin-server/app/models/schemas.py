from pydantic import BaseModel
from typing import Optional, List, Literal
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
    model_tier: Optional[Literal["flash", "standard", "pro"]] = None  # 模型级别覆盖

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


# 记忆系统模型
class MemoryUpdateRequest(BaseModel):
    content: str  # Markdown格式的记忆文本

class MemoryResponse(BaseModel):
    content: str
    updated_at: Optional[datetime] = None

class MemoryBackupItem(BaseModel):
    version: int
    timestamp: datetime
    content_preview: str  # 前100字预览

class MemoryBackupListResponse(BaseModel):
    backups: List[MemoryBackupItem]

class MemoryRollbackRequest(BaseModel):
    version: int

class MemoryConsolidationStatus(BaseModel):
    last_consolidation: Optional[datetime] = None
    pending_sessions: int  # 等待整理的超时会话数
