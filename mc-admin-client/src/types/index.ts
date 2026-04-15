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

// WebSocket消息类型
export interface WSMessage {
  type: 'auth' | 'status' | 'command' | 'result' | 'chat_response' | 'auth_success' | 'auth_response' | 'auth_failed';
  server_id?: string;
  token?: string;
  timestamp?: number;
  data?: any;
  id?: string;
  action?: string;
  payload?: any;
  command_id?: string;
  success?: boolean;
  output?: string;
  message?: string;
}

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

// AI聊天API响应
export interface ChatApiResponse {
  message: string;
  command_executed?: any;
  review?: ReviewInfo;
  timestamp: string;
}

// API响应
export interface ApiResponse<T = any> {
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
