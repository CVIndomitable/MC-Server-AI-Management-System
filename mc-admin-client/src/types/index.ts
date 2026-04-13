// 服务器状态数据类型
export interface ServerStatus {
  tps: number;
  players: string[];
  memory_used_mb: number;
  memory_max_mb: number;
  recent_errors: string[];
  timestamp: number;
}

// WebSocket消息类型
export interface WSMessage {
  type: 'status' | 'command' | 'result' | 'chat_response';
  server_id?: string;
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

// 聊天消息
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
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

export interface BindRequestInfo {
  id: number;
  username: string;
  server_id: string;
  status: string; // pending | approved | rejected
  created_at: string;
  resolved_at?: string;
  resolved_by?: string;
}
