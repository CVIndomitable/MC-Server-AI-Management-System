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
      const message = error.response?.data?.message || error.message || '登录失败';
      const statusCode = error.response?.status;

      if (statusCode === 401) {
        return { success: false, error: '用户名或密码错误' };
      } else if (statusCode === 500) {
        return { success: false, error: '服务器错误，请稍后重试' };
      } else if (error.code === 'ECONNABORTED') {
        return { success: false, error: '请求超时，请检查网络连接' };
      } else if (!error.response) {
        return { success: false, error: '网络连接失败，请检查网络' };
      }

      return { success: false, error: message };
    }
  }

  // 发送聊天消息
  async sendChatMessage(message: string, serverId: string): Promise<ApiResponse<ChatMessage>> {
    try {
      const response = await this.client.post('/api/v1/chat', {
        message,
        server_id: serverId,
      });
      return { success: true, data: response.data };
    } catch (error: any) {
      const errorMessage = error.response?.data?.message || error.message || '发送失败';

      if (!error.response) {
        return { success: false, error: '网络连接失败' };
      } else if (error.response.status === 401) {
        return { success: false, error: '认证失败，请重新登录' };
      }

      return { success: false, error: errorMessage };
    }
  }

  // 获取服务器状态
  async getServerStatus(serverId: string): Promise<ApiResponse> {
    try {
      const response = await this.client.get(`/api/v1/servers/${serverId}/status`);
      return { success: true, data: response.data };
    } catch (error: any) {
      const errorMessage = error.response?.data?.message || error.message || '获取状态失败';

      if (!error.response) {
        return { success: false, error: '网络连接失败' };
      }

      return { success: false, error: errorMessage };
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
      const errorMessage = error.response?.data?.message || error.message || '操作失败';

      if (!error.response) {
        return { success: false, error: '网络连接失败' };
      } else if (error.response.status === 403) {
        return { success: false, error: '权限不足' };
      }

      return { success: false, error: errorMessage };
    }
  }
}

export default new ApiService();
