from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Dict
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
    message: str = Field(max_length=2000)
    server_id: str
    query_only: bool = False  # 仅查询模式：AI只建议不执行
    model_tier: Optional[Literal["flash", "standard", "pro"]] = None  # 模型级别覆盖

class ReviewInfo(BaseModel):
    status: str  # "approved" | "rejected" | "pending_confirmation"
    risk_level: str  # "low" | "medium" | "high"
    reviewed_by: str = "rule_engine"  # "rule_engine" | "ai_reviewer" | "user"
    reason: Optional[str] = None
    suggestion: Optional[str] = None
    pending_id: Optional[str] = None
    command: Optional[str] = None
    expires_in: Optional[int] = None

class ChatResponse(BaseModel):
    message: str
    command_executed: Optional[dict] = None
    review: Optional[ReviewInfo] = None
    timestamp: datetime
    # 供应商降级提示：主供应商不可用、已切换到低优先级时为 True
    degraded: bool = False
    degraded_message: Optional[str] = None

class ServerStatus(BaseModel):
    server_id: str
    tps: float
    players: List[str]
    memory_used_mb: int
    memory_max_mb: int
    cpu_process: Optional[float] = None  # JVM进程CPU使用率(%)
    cpu_system: Optional[float] = None   # 系统总CPU使用率(%)
    cpu_cores: Optional[int] = None      # CPU核心数
    recent_errors: List[str]
    last_update: Optional[datetime] = None
    online: bool

class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=32, pattern=r'^[a-zA-Z0-9_]+$')
    password: str = Field(min_length=6)
    role: str = "user"

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class ResetPasswordRequest(BaseModel):
    new_password: str

class UserInfo(BaseModel):
    username: str
    role: str
    created_at: str

class UserListResponse(BaseModel):
    users: List[UserInfo]


# 服务器管理模型
class ServerInfo(BaseModel):
    server_id: str
    name: str
    online: bool = False
    created_at: str
    last_seen_at: Optional[str] = None

class UserServerInfo(BaseModel):
    server_id: str
    name: str
    role: str  # owner | admin
    online: bool = False
    bound_at: str

class UserServerListResponse(BaseModel):
    servers: List[UserServerInfo]

class UnboundServerListResponse(BaseModel):
    servers: List[ServerInfo]

class BindRequestInfo(BaseModel):
    id: int
    username: str
    server_id: str
    status: str  # pending | approved | rejected
    created_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None

class BindRequestListResponse(BaseModel):
    requests: List[BindRequestInfo]

class UpdateServerNameRequest(BaseModel):
    name: str

class ServerUserInfo(BaseModel):
    username: str
    role: str
    bound_at: str

class ServerUserListResponse(BaseModel):
    users: List[ServerUserInfo]


# 记忆系统模型
class MemoryEntry(BaseModel):
    id: Optional[str] = None  # 自动生成
    tags: List[str] = []
    content: str
    pinned: bool = False

class MemoryUpdateRequest(BaseModel):
    content: str  # Markdown格式的记忆文本（向后兼容）
    entries: Optional[List[MemoryEntry]] = None  # 结构化条目（可选）

class MemoryResponse(BaseModel):
    content: str
    entries: Optional[List[MemoryEntry]] = None  # 结构化条目（如有）
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


# LLM API 供应商管理
class ApiProviderInfo(BaseModel):
    id: int
    name: str
    base_url: str
    api_key_tail: str  # key 的最后 4 位，用于识别（完整 key 不返回客户端）
    priority: int
    enabled: bool
    # 模型名映射：canonical 模型名 → 该 provider 实际模型名，None 表示无映射（原样透传）
    model_map: Optional[Dict[str, str]] = None
    created_at: str
    updated_at: str

class ApiProviderListResponse(BaseModel):
    providers: List[ApiProviderInfo]

class ApiProviderCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    base_url: str = Field(min_length=1, max_length=512)
    api_key: str = Field(min_length=1, max_length=512)
    priority: int = 100
    enabled: bool = True
    model_map: Optional[Dict[str, str]] = None

class ApiProviderUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=512)
    api_key: Optional[str] = Field(default=None, min_length=1, max_length=512)  # 留空表示不改
    priority: Optional[int] = None
    enabled: Optional[bool] = None
    model_map: Optional[Dict[str, str]] = None  # 传 {} 清空映射，None 表示不改
    clear_model_map: bool = False
