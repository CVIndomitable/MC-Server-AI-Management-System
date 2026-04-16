// 服务器状态数据类型
export interface ServerStatus {
  tps: number;
  players: string[];
  memory_used_mb: number;
  memory_max_mb: number;
  cpu_process?: number;  // JVM进程CPU使用率(%)
  cpu_system?: number;   // 系统总CPU使用率(%)
  cpu_cores?: number;    // CPU核心数
  recent_errors: string[];
  timestamp: number;
}

// WebSocket消息类型（使用 discriminated union 替代宽泛的可选字段）
export type WSMessage =
  | { type: 'auth'; token: string; server_id: string }
  | { type: 'auth_success'; server_id?: string }
  | { type: 'auth_response'; server_id?: string }
  | { type: 'auth_failed'; message?: string }
  | { type: 'status'; server_id?: string; data: ServerStatus; timestamp?: number }
  | { type: 'command'; id: string; action: string; payload: Record<string, unknown> }
  | { type: 'result'; command_id: string; success: boolean; output: string; server_id?: string }
  | { type: 'chat_response'; message: string; server_id?: string };

// 聊天消息（客户端展示用）
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  review?: ReviewInfo;
}

// 审核信息
export interface ReviewInfo {
  status: 'approved' | 'rejected' | 'pending_confirmation';
  risk_level: 'low' | 'medium' | 'high';
  reviewed_by: string;
  reason?: string;
  suggestion?: string;
  pending_id?: string;
  command?: string;
  expires_in?: number;
}

// 命令执行结果
export interface CommandExecuted {
  tool: string;
  input: Record<string, unknown>;
  result: { success: boolean; output: string };
}

// AI聊天API响应
export interface ChatApiResponse {
  message: string;
  command_executed?: CommandExecuted;
  review?: ReviewInfo;
  timestamp: string;
  degraded?: boolean;
  degraded_message?: string;
}

// LLM 供应商管理
export interface ApiProviderInfo {
  id: number;
  name: string;
  base_url: string;
  api_key_tail: string;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ApiProviderPayload {
  name?: string;
  base_url?: string;
  api_key?: string;  // 留空表示不改
  priority?: number;
  enabled?: boolean;
}

// API响应
export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
}

// 用户认证
export interface AuthCredentials {
  username: string;
  password: string;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
}

// 用户信息
export interface UserInfo {
  username: string;
  role: string;
  created_at: string;
}

// 模型级别
export type ModelTier = 'flash' | 'standard' | 'pro';

// 服务器管理
export interface UserServerInfo {
  server_id: string;
  name: string;
  role: string; // owner | admin
  online: boolean;
  bound_at: string;
}

export interface ServerInfo {
  server_id: string;
  name: string;
  online: boolean;
  created_at: string;
  last_seen_at?: string;
}

export interface ServerUserInfo {
  username: string;
  role: string;
  bound_at: string;
}

export interface BindRequestInfo {
  id: number;
  username: string;
  server_id: string;
  status: string; // pending | approved | rejected
  created_at: string;
  resolved_at?: string;
  resolved_by?: string;
}

// 已保存的账号
export interface SavedAccount {
  username: string;
  lastUsed: number; // timestamp
}

// 记忆系统
export interface MemoryResponse {
  content: string;
  updated_at?: string;
}
