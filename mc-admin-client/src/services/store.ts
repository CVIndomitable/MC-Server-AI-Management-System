import { create } from 'zustand';
import { ServerStatus, ChatMessage } from '../types';
import apiService from '../services/api';
import wsService from '../services/websocket';

interface AppState {
  // 认证状态
  isAuthenticated: boolean;
  token: string | null;
  serverId: string;

  // 服务器状态
  serverStatus: ServerStatus | null;

  // 聊天消息
  chatMessages: ChatMessage[];

  // UI状态
  isLoading: boolean;
  error: string | null;

  // Actions
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
  setServerId: (id: string) => void;
  updateServerStatus: (status: ServerStatus) => void;
  addChatMessage: (message: ChatMessage) => void;
  sendMessage: (content: string) => Promise<void>;
  connectWebSocket: () => void;
  disconnectWebSocket: () => void;
  setError: (error: string | null) => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  isAuthenticated: false,
  token: null,
  serverId: 'srv_001', // 默认服务器ID
  serverStatus: null,
  chatMessages: [],
  isLoading: false,
  error: null,

  login: async (username: string, password: string) => {
    set({ isLoading: true, error: null });

    const result = await apiService.login({ username, password });

    if (result.success && result.data) {
      const { token } = result.data;
      apiService.setToken(token);
      set({
        isAuthenticated: true,
        token,
        isLoading: false
      });

      // 登录成功后连接WebSocket
      get().connectWebSocket();
      return true;
    } else {
      set({
        isLoading: false,
        error: result.error || '登录失败'
      });
      return false;
    }
  },

  logout: () => {
    get().disconnectWebSocket();
    apiService.clearToken();
    set({
      isAuthenticated: false,
      token: null,
      chatMessages: [],
      serverStatus: null
    });
  },

  setServerId: (id: string) => {
    set({ serverId: id });
  },

  updateServerStatus: (status: ServerStatus) => {
    set({ serverStatus: status });
  },

  addChatMessage: (message: ChatMessage) => {
    set(state => ({
      chatMessages: [...state.chatMessages, message]
    }));
  },

  sendMessage: async (content: string) => {
    const { serverId, token, addChatMessage } = get();

    // 添加用户消息
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: Date.now(),
    };
    addChatMessage(userMessage);

    set({ isLoading: true });

    const result = await apiService.sendChatMessage(content, serverId);

    if (result.success && result.data) {
      addChatMessage(result.data);
    } else {
      // 添加错误消息
      const errorMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `错误: ${result.error}`,
        timestamp: Date.now(),
      };
      addChatMessage(errorMessage);
    }

    set({ isLoading: false });
  },

  connectWebSocket: () => {
    const { token, serverId, updateServerStatus, addChatMessage } = get();

    if (!token) return;

    wsService.connect(token, serverId);

    // 注册消息处理器
    wsService.addMessageHandler((message) => {
      if (message.type === 'status' && message.data) {
        updateServerStatus(message.data);
      } else if (message.type === 'chat_response' && message.message) {
        const chatMessage: ChatMessage = {
          id: Date.now().toString(),
          role: 'assistant',
          content: message.message,
          timestamp: Date.now(),
        };
        addChatMessage(chatMessage);
      }
    });
  },

  disconnectWebSocket: () => {
    wsService.disconnect();
  },

  setError: (error: string | null) => {
    set({ error });
  },
}));
