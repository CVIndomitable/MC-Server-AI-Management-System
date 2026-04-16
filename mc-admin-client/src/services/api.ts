import axios, { AxiosInstance, AxiosError } from 'axios';
import { CONFIG } from '../utils/config';
import {
  ApiResponse, AuthCredentials, AuthToken, ChatApiResponse,
  UserServerInfo, ServerInfo, BindRequestInfo, ServerUserInfo,
  UserInfo, ModelTier, MemoryResponse, ReviewInfo,
  ApiProviderInfo, ApiProviderPayload,
} from '../types';

// 全局登出回调（由 store 注入）
let onUnauthorized: (() => void) | null = null;

export function setOnUnauthorized(callback: () => void) {
  onUnauthorized = callback;
}

class ApiService {
  private client: AxiosInstance;
  private token: string | null = null;
  private pendingRequests = new Set<string>();

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

    // 响应拦截器 - 全局处理401
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        if (error.response?.status === 401 && this.token) {
          // 非登录请求的401 → 触发全局登出
          if (onUnauthorized) {
            onUnauthorized();
          }
        }
        return Promise.reject(error);
      }
    );
  }

  setToken(token: string) {
    this.token = token;
  }

  clearToken() {
    this.token = null;
  }

  /**
   * 请求去重：防止快速重复点击导致多次请求
   */
  private dedup<T>(key: string, fn: () => Promise<ApiResponse<T>>): Promise<ApiResponse<T>> {
    if (this.pendingRequests.has(key)) {
      return Promise.resolve({ success: false, error: '请求处理中，请勿重复操作' });
    }
    this.pendingRequests.add(key);
    return fn().finally(() => this.pendingRequests.delete(key));
  }

  // ---- 用户认证 ----

  async login(credentials: AuthCredentials): Promise<ApiResponse<AuthToken>> {
    try {
      const response = await this.client.post('/api/v1/auth/login', credentials);
      return { success: true, data: response.data };
    } catch (error) {
      const axiosErr = error as AxiosError<{ detail?: string }>;
      if (axiosErr.response?.status === 401) {
        return { success: false, error: '用户名或密码错误' };
      }
      return { success: false, error: this.getChineseError(axiosErr, '登录失败') };
    }
  }

  async register(username: string, password: string, role: string = 'user'): Promise<ApiResponse<UserInfo>> {
    try {
      const response = await this.client.post('/api/v1/auth/register', { username, password, role });
      return { success: true, data: response.data };
    } catch (error) {
      const axiosErr = error as AxiosError<{ detail?: string }>;
      if (axiosErr.response?.status === 409) {
        return { success: false, error: '用户名已存在' };
      }
      return { success: false, error: this.getChineseError(axiosErr, '注册失败') };
    }
  }

  async changePassword(oldPassword: string, newPassword: string): Promise<ApiResponse> {
    try {
      const response = await this.client.put('/api/v1/auth/password', {
        old_password: oldPassword,
        new_password: newPassword,
      });
      return { success: true, data: response.data };
    } catch (error) {
      const axiosErr = error as AxiosError<{ detail?: string }>;
      if (axiosErr.response?.status === 400) {
        return { success: false, error: axiosErr.response.data?.detail || '旧密码不正确' };
      }
      return { success: false, error: this.getChineseError(axiosErr, '修改密码失败') };
    }
  }

  async resetPassword(username: string, newPassword: string): Promise<ApiResponse> {
    try {
      const response = await this.client.put(`/api/v1/auth/users/${username}/password`, {
        new_password: newPassword,
      });
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '重置密码失败') };
    }
  }

  async listUsers(): Promise<ApiResponse<{ users: UserInfo[] }>> {
    try {
      const response = await this.client.get('/api/v1/auth/users');
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '获取用户列表失败') };
    }
  }

  async deleteUser(username: string): Promise<ApiResponse> {
    try {
      const response = await this.client.delete(`/api/v1/auth/users/${username}`);
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '删除用户失败') };
    }
  }

  // ---- 聊天 ----

  async sendChatMessage(
    message: string,
    serverId: string,
    queryOnly: boolean = false,
    modelTier?: ModelTier,
  ): Promise<ApiResponse<ChatApiResponse>> {
    return this.dedup(`chat:${serverId}`, async () => {
      try {
        const response = await this.client.post('/api/v1/chat', {
          message,
          server_id: serverId,
          query_only: queryOnly,
          model_tier: modelTier || null,
        });
        return { success: true, data: response.data };
      } catch (error) {
        const axiosErr = error as AxiosError<{ detail?: string }>;
        if (axiosErr.response?.status === 401) {
          return { success: false, error: '认证已过期，请重新登录' };
        }
        if (axiosErr.response?.status === 503) {
          return { success: false, error: '服务器未连接' };
        }
        if (axiosErr.response?.status === 429) {
          return { success: false, error: '请求过于频繁，请稍后再试' };
        }
        return { success: false, error: this.getChineseError(axiosErr, '发送消息失败') };
      }
    });
  }

  // ---- 命令审核确认 ----

  async confirmPendingCommand(
    pendingId: string,
    action: 'approve' | 'reject',
  ): Promise<ApiResponse<{ message: string; output?: string; command?: string }>> {
    return this.dedup(`confirm:${pendingId}`, async () => {
      try {
        const response = await this.client.post(
          `/api/v1/chat/confirm/${pendingId}?action=${action}`
        );
        return { success: true, data: response.data };
      } catch (error) {
        const axiosErr = error as AxiosError<{ detail?: string }>;
        if (axiosErr.response?.status === 404) {
          return { success: false, error: '确认请求已过期' };
        }
        return { success: false, error: this.getChineseError(axiosErr, '操作失败') };
      }
    });
  }

  // ---- 服务器状态 ----

  async getServerStatus(serverId: string): Promise<ApiResponse> {
    try {
      const response = await this.client.get(`/api/v1/status/${serverId}`);
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '获取状态失败') };
    }
  }

  // ---- 服务器管理 ----

  async getMyServers(): Promise<ApiResponse<{ servers: UserServerInfo[] }>> {
    try {
      const response = await this.client.get('/api/v1/servers/my');
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '获取服务器列表失败') };
    }
  }

  async getUnboundServers(): Promise<ApiResponse<{ servers: ServerInfo[] }>> {
    try {
      const response = await this.client.get('/api/v1/servers/unbound');
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '获取未绑定服务器失败') };
    }
  }

  async bindServer(serverId: string): Promise<ApiResponse<UserServerInfo>> {
    try {
      const response = await this.client.post(`/api/v1/servers/${serverId}/bind`);
      if (response.status === 202) {
        return { success: false, error: response.data?.detail || '已提交绑定申请，等待主管理员审批' };
      }
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '绑定服务器失败') };
    }
  }

  async getBindRequests(serverId: string): Promise<ApiResponse<{ requests: BindRequestInfo[] }>> {
    try {
      const response = await this.client.get(`/api/v1/servers/${serverId}/requests`);
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '获取绑定申请失败') };
    }
  }

  async approveBindRequest(serverId: string, requestId: number): Promise<ApiResponse> {
    try {
      const response = await this.client.post(`/api/v1/servers/${serverId}/requests/${requestId}/approve`);
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '审批失败') };
    }
  }

  async rejectBindRequest(serverId: string, requestId: number): Promise<ApiResponse> {
    try {
      const response = await this.client.post(`/api/v1/servers/${serverId}/requests/${requestId}/reject`);
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '审批失败') };
    }
  }

  async listServerUsers(serverId: string): Promise<ApiResponse<{ users: ServerUserInfo[] }>> {
    try {
      const response = await this.client.get(`/api/v1/servers/${serverId}/users`);
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '获取管理员列表失败') };
    }
  }

  async updateServerName(serverId: string, name: string): Promise<ApiResponse> {
    try {
      const response = await this.client.put(`/api/v1/servers/${serverId}/name`, { name });
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '修改名称失败') };
    }
  }

  async unbindUser(serverId: string, username: string): Promise<ApiResponse> {
    try {
      const response = await this.client.delete(`/api/v1/servers/${serverId}/unbind/${username}`);
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '解绑失败') };
    }
  }

  // ---- 记忆系统 ----

  async getMemory(type: 'global' | 'admin' | 'server', id?: string): Promise<ApiResponse<MemoryResponse>> {
    try {
      const path = type === 'global' ? '/api/v1/memory/global' : `/api/v1/memory/${type}/${id}`;
      const response = await this.client.get(path);
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '获取记忆失败') };
    }
  }

  async updateMemory(type: 'global' | 'admin' | 'server', id: string, content: string): Promise<ApiResponse> {
    try {
      const path = type === 'global' ? '/api/v1/memory/global' : `/api/v1/memory/${type}/${id}`;
      const response = await this.client.put(path, { content });
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError, '更新记忆失败') };
    }
  }

  // ---- LLM 供应商管理（仅管理员） ----

  async listProviders(): Promise<ApiResponse<{ providers: ApiProviderInfo[] }>> {
    try {
      const response = await this.client.get('/api/v1/admin/providers');
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError<{ detail?: string }>, '获取供应商列表失败') };
    }
  }

  async createProvider(payload: ApiProviderPayload): Promise<ApiResponse<ApiProviderInfo>> {
    try {
      const response = await this.client.post('/api/v1/admin/providers', payload);
      return { success: true, data: response.data };
    } catch (error) {
      const axiosErr = error as AxiosError<{ detail?: string }>;
      if (axiosErr.response?.status === 409) {
        return { success: false, error: axiosErr.response.data?.detail || '名称已存在' };
      }
      return { success: false, error: this.getChineseError(axiosErr, '创建供应商失败') };
    }
  }

  async updateProvider(providerId: number, payload: ApiProviderPayload): Promise<ApiResponse<ApiProviderInfo>> {
    try {
      const response = await this.client.put(`/api/v1/admin/providers/${providerId}`, payload);
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError<{ detail?: string }>, '更新供应商失败') };
    }
  }

  async deleteProvider(providerId: number): Promise<ApiResponse> {
    try {
      const response = await this.client.delete(`/api/v1/admin/providers/${providerId}`);
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: this.getChineseError(error as AxiosError<{ detail?: string }>, '删除供应商失败') };
    }
  }

  // 将错误信息转为中文
  private getChineseError(error: AxiosError<{ detail?: string }>, fallback: string): string {
    if (!error.response) return '无法连接服务器，请检查网络';
    if (error.code === 'ECONNABORTED') return '请求超时，请稍后重试';
    const status = error.response?.status;
    if (status === 400) return error.response.data?.detail || '请求参数错误';
    if (status === 401) return '认证已过期，请重新登录';
    if (status === 403) return '权限不足';
    if (status === 404) return '请求的资源不存在';
    if (status === 409) return error.response.data?.detail || '资源冲突';
    if (status === 429) return '请求过于频繁，请稍后重试';
    if (status && status >= 500) return '服务器内部错误，请稍后重试';
    return fallback;
  }
}

export default new ApiService();
