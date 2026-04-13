import axios, { AxiosInstance } from 'axios';
import { CONFIG } from '../utils/config';
import { ApiResponse, AuthCredentials, AuthToken, ChatMessage } from '../types';

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

  // 用户认证
  async login(credentials: AuthCredentials): Promise<ApiResponse<AuthToken>> {
    try {
      const response = await this.client.post('/api/v1/auth/login', credentials);
      return { success: true, data: response.data };
    } catch (error: any) {
      const statusCode = error.response?.status;

      if (statusCode === 401) {
        return { success: false, error: '用户名或密码错误' };
      } else if (statusCode === 500) {
        return { success: false, error: '服务器错误，请稍后重试' };
      } else if (error.code === 'ECONNABORTED') {
        return { success: false, error: '请求超时，请检查网络连接' };
      } else if (!error.response) {
        return { success: false, error: '无法连接服务器，请检查网络' };
      }

      return { success: false, error: this.getChineseError(error, '登录失败') };
    }
  }

  // 发送聊天消息
  async sendChatMessage(message: string, serverId: string, queryOnly: boolean = false): Promise<ApiResponse<ChatMessage>> {
    try {
      const response = await this.client.post('/api/v1/chat', {
        message,
        server_id: serverId,
        query_only: queryOnly,
      });
      return { success: true, data: response.data };
    } catch (error: any) {
      if (!error.response) {
        return { success: false, error: '无法连接服务器，请检查网络' };
      } else if (error.code === 'ECONNABORTED') {
        return { success: false, error: '请求超时，请稍后重试' };
      } else if (error.response.status === 401) {
        return { success: false, error: '认证已过期，请重新登录' };
      }

      return { success: false, error: this.getChineseError(error, '发送消息失败') };
    }
  }

  // 获取服务器状态
  async getServerStatus(serverId: string): Promise<ApiResponse> {
    try {
      const response = await this.client.get(`/api/v1/servers/${serverId}/status`);
      return { success: true, data: response.data };
    } catch (error: any) {
      if (!error.response) {
        return { success: false, error: '无法连接服务器，请检查网络' };
      } else if (error.code === 'ECONNABORTED') {
        return { success: false, error: '请求超时，请稍后重试' };
      }

      return { success: false, error: this.getChineseError(error, '获取状态失败') };
    }
  }

  // 执行快捷操作
  async executeQuickAction(serverId: string, action: string, params?: any): Promise<ApiResponse> {
    try {
      const response = await this.client.post(`/api/v1/servers/${serverId}/actions`, {
        action,
        params,
      });
      return { success: true, data: response.data };
    } catch (error: any) {
      if (!error.response) {
        return { success: false, error: '无法连接服务器，请检查网络' };
      } else if (error.code === 'ECONNABORTED') {
        return { success: false, error: '请求超时，请稍后重试' };
      } else if (error.response.status === 403) {
        return { success: false, error: '权限不足，无法执行此操作' };
      }

      return { success: false, error: this.getChineseError(error, '操作执行失败') };
    }
  }

  // 将错误信息转为中文，避免暴露英文错误给用户
  private getChineseError(error: any, fallback: string): string {
    const status = error.response?.status;
    if (status === 400) return '请求参数错误';
    if (status === 401) return '认证已过期，请重新登录';
    if (status === 403) return '权限不足';
    if (status === 404) return '请求的资源不存在';
    if (status === 429) return '请求过于频繁，请稍后重试';
    if (status >= 500) return '服务器内部错误，请稍后重试';
    return fallback;
  }
}

export default new ApiService();
