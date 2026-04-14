import axios, { AxiosInstance } from 'axios';
import { CONFIG } from '../utils/config';
import {
  ApiResponse, AuthCredentials, AuthToken, ChatApiResponse,
  UserServerInfo, ServerInfo, BindRequestInfo, ServerUserInfo,
  UserInfo, ModelTier, MemoryResponse, ReviewInfo,
} from '../types';

class ApiService {
  private client: AxiosInstance;
  private token: string | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: CONFIG.apiBaseUrl,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // 请求拦截器 - 自动添加token
    this.client.interceptors.request.use((config) => {
      if (this.token) {
        config.headers.Authorization = `Bearer ${this.token}`;
      }
      return config;
    });
  }

  setToken(token: string) {
    this.token = token;
  }

  clearToken() {
    this.token = null;
  }

  // ---- 用户认证 ----

  async login(credentials: AuthCredentials): Promise<ApiResponse<AuthToken>> {
    try {
      const url = `${this.client.defaults.baseURL}/api/v1/auth/login`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
      });
      const data = await res.json();
      if (!res.ok) {
        if (res.status === 401) return { success: false, error: '用户名或密码错误' };
        return { success: false, error: data.detail || '登录失败' };
      }
      return { success: true, data };
    } catch (error: any) {
      return { success: false, error: '无法连接服务器，请检查网络' };
    }
  }

  async register(username: string, password: string, role: string = 'user'): Promise<ApiResponse<UserInfo>> {
    try {
      const response = await this.client.post('/api/v1/auth/register', { username, password, role });
      return { success: true, data: response.data };
    } catch (error: any) {
      if (error.response?.status === 409) {
        return { success: false, error: '用户名已存在' };
      }
      return { success: false, error: this.getChineseError(error, '注册失败') };
    }
  }

  async changePassword(oldPassword: string, newPassword: string): Promise<ApiResponse> {
    try {
      const response = await this.client.put('/api/v1/auth/password', {
        old_password: oldPassword,
        new_password: newPassword,
      });
      return { success: true, data: response.data };
    } catch (error: any) {
      if (error.response?.status === 400) {
        return { success: false, error: error.response.data?.detail || '旧密码不正确' };
      }
      return { success: false, error: this.getChineseError(error, '修改密码失败') };
    }
  }

  async resetPassword(username: string, newPassword: string): Promise<ApiResponse> {
    try {
      const response = await this.client.put(`/api/v1/auth/users/${username}/password`, {
        new_password: newPassword,
      });
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '重置密码失败') };
    }
  }

  async listUsers(): Promise<ApiResponse<{ users: UserInfo[] }>> {
    try {
      const response = await this.client.get('/api/v1/auth/users');
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '获取用户列表失败') };
    }
  }

  async deleteUser(username: string): Promise<ApiResponse> {
    try {
      const response = await this.client.delete(`/api/v1/auth/users/${username}`);
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '删除用户失败') };
    }
  }

  // ---- 聊天 ----

  async sendChatMessage(
    message: string,
    serverId: string,
    queryOnly: boolean = false,
    modelTier?: ModelTier,
  ): Promise<ApiResponse<ChatApiResponse>> {
    try {
      const response = await this.client.post('/api/v1/chat', {
        message,
        server_id: serverId,
        query_only: queryOnly,
        model_tier: modelTier || null,
      });
      return { success: true, data: response.data };
    } catch (error: any) {
      if (error.response?.status === 401) {
        return { success: false, error: '认证已过期，请重新登录' };
      }
      if (error.response?.status === 503) {
        return { success: false, error: '服务器未连接' };
      }
      return { success: false, error: this.getChineseError(error, '发送消息失败') };
    }
  }

  // ---- 命令审核确认 ----

  async confirmPendingCommand(
    pendingId: string,
    action: 'approve' | 'reject',
  ): Promise<ApiResponse<{ message: string; output?: string; command?: string }>> {
    try {
      const response = await this.client.post(
        `/api/v1/chat/confirm/${pendingId}?action=${action}`
      );
      return { success: true, data: response.data };
    } catch (error: any) {
      if (error.response?.status === 404) {
        return { success: false, error: '确认请求已过期' };
      }
      return { success: false, error: this.getChineseError(error, '操作失败') };
    }
  }

  // ---- 服务器状态 ----

  async getServerStatus(serverId: string): Promise<ApiResponse> {
    try {
      const response = await this.client.get(`/api/v1/status/${serverId}`);
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '获取状态失败') };
    }
  }

  // ---- 服务器管理 ----

  async getMyServers(): Promise<ApiResponse<{ servers: UserServerInfo[] }>> {
    try {
      const response = await this.client.get('/api/v1/servers/my');
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '获取服务器列表失败') };
    }
  }

  async getUnboundServers(): Promise<ApiResponse<{ servers: ServerInfo[] }>> {
    try {
      const response = await this.client.get('/api/v1/servers/unbound');
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '获取未绑定服务器失败') };
    }
  }

  async bindServer(serverId: string): Promise<ApiResponse<UserServerInfo>> {
    try {
      const response = await this.client.post(`/api/v1/servers/${serverId}/bind`);
      if (response.status === 202) {
        return { success: false, error: response.data?.detail || '已提交绑定申请，等待主管理员审批' };
      }
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '绑定服务器失败') };
    }
  }

  async getBindRequests(serverId: string): Promise<ApiResponse<{ requests: BindRequestInfo[] }>> {
    try {
      const response = await this.client.get(`/api/v1/servers/${serverId}/requests`);
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '获取绑定申请失败') };
    }
  }

  async approveBindRequest(serverId: string, requestId: number): Promise<ApiResponse> {
    try {
      const response = await this.client.post(`/api/v1/servers/${serverId}/requests/${requestId}/approve`);
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '审批失败') };
    }
  }

  async rejectBindRequest(serverId: string, requestId: number): Promise<ApiResponse> {
    try {
      const response = await this.client.post(`/api/v1/servers/${serverId}/requests/${requestId}/reject`);
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '审批失败') };
    }
  }

  async listServerUsers(serverId: string): Promise<ApiResponse<{ users: ServerUserInfo[] }>> {
    try {
      const response = await this.client.get(`/api/v1/servers/${serverId}/users`);
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '获取管理员列表失败') };
    }
  }

  async updateServerName(serverId: string, name: string): Promise<ApiResponse> {
    try {
      const response = await this.client.put(`/api/v1/servers/${serverId}/name`, { name });
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '修改名称失败') };
    }
  }

  async unbindUser(serverId: string, username: string): Promise<ApiResponse> {
    try {
      const response = await this.client.delete(`/api/v1/servers/${serverId}/unbind/${username}`);
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '解绑失败') };
    }
  }

  // ---- 记忆系统 ----

  async getMemory(type: 'global' | 'admin' | 'server', id?: string): Promise<ApiResponse<MemoryResponse>> {
    try {
      const path = type === 'global' ? '/api/v1/memory/global' : `/api/v1/memory/${type}/${id}`;
      const response = await this.client.get(path);
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '获取记忆失败') };
    }
  }

  async updateMemory(type: 'global' | 'admin' | 'server', id: string, content: string): Promise<ApiResponse> {
    try {
      const path = type === 'global' ? '/api/v1/memory/global' : `/api/v1/memory/${type}/${id}`;
      const response = await this.client.put(path, { content });
      return { success: true, data: response.data };
    } catch (error: any) {
      return { success: false, error: this.getChineseError(error, '更新记忆失败') };
    }
  }

  // 将错误信息转为中文
  private getChineseError(error: any, fallback: string): string {
    if (!error.response) return '无法连接服务器，请检查网络';
    if (error.code === 'ECONNABORTED') return '请求超时，请稍后重试';
    const status = error.response?.status;
    if (status === 400) return error.response.data?.detail || '请求参数错误';
    if (status === 401) return '认证已过期，请重新登录';
    if (status === 403) return '权限不足';
    if (status === 404) return '请求的资源不存在';
    if (status === 409) return error.response.data?.detail || '资源冲突';
    if (status === 429) return '请求过于频繁，请稍后重试';
    if (status >= 500) return '服务器内部错误，请稍后重试';
    return fallback;
  }
}

export default new ApiService();
