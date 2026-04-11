import { create } from 'zustand';
import { v4 as uuidv4 } from 'uuid';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { ServerStatus, ChatMessage } from '../types';
import apiService from '../services/api';
import wsService from '../services/websocket';

const TOKEN_KEY = '@mc_admin_token';
const SERVER_ID_KEY = '@mc_admin_server_id';

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
  wsConnected: boolean;

  // WebSocket消息处理器引用
  wsMessageHandler: ((message: any) => void) | null;

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
  restoreSession: () => Promise<void>;
}

export const useAppStore = create<AppState>((set, get) => ({
  isAuthenticated: false,
  token: null,
  serverId: 'srv_001', // 默认服务器ID
  serverStatus: null,
  chatMessages: [],
  isLoading: false,
  error: null,
  wsConnected: false,
  wsMessageHandler: null,

  login: async (username: string, password: string) => {
    set({ isLoading: true, error: null });

    const result = await apiService.login({ username, password });

    if (result.success && result.data) {
      const { token } = result.data;
      apiService.setToken(token);

      // 持久化token
      await AsyncStorage.setItem(TOKEN_KEY, token);

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

    // 清除持久化数据
    AsyncStorage.removeItem(TOKEN_KEY);

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
      id: uuidv4(),
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
        id: uuidv4(),
        role: 'assistant',
        content: `错误: ${result.error}`,
        timestamp: Date.now(),
      };
      addChatMessage(errorMessage);
    }

    set({ isLoading: false });
  },

  connectWebSocket: () => {
    const { token, serverId, updateServerStatus, addChatMessage, wsMessageHandler } = get();

    if (!token) return;

    // 清理旧的处理器
    if (wsMessageHandler) {
      wsService.removeMessageHandler(wsMessageHandler);
    }

    wsService.connect(token, serverId);

    // 创建并保存新的消息处理器
    const handler = (message: any) => {
      if (message.type === 'status' && message.data) {
        updateServerStatus(message.data);
      } else if (message.type === 'chat_response' && message.message) {
        const chatMessage: ChatMessage = {
          id: uuidv4(),
          role: 'assistant',
          content: message.message,
          timestamp: Date.now(),
        };
        addChatMessage(chatMessage);
      }
    };

    // 注册状态处理器
    const statusHandler = (connected: boolean) => {
      set({ wsConnected: connected });
    };

    wsService.addMessageHandler(handler);
    wsService.addStatusHandler(statusHandler);
    set({ wsMessageHandler: handler });
  },

  disconnectWebSocket: () => {
    const { wsMessageHandler } = get();

    // 清理消息处理器
    if (wsMessageHandler) {
      wsService.removeMessageHandler(wsMessageHandler);
      set({ wsMessageHandler: null });
    }

    wsService.disconnect();
  },

  setError: (error: string | null) => {
    set({ error });
  },

  restoreSession: async () => {
    try {
      const token = await AsyncStorage.getItem(TOKEN_KEY);
      const serverId = await AsyncStorage.getItem(SERVER_ID_KEY);

      if (token) {
        apiService.setToken(token);
        set({
          isAuthenticated: true,
          token,
          serverId: serverId || 'srv_001',
        });

        // 恢复会话后连接WebSocket
        get().connectWebSocket();
      }
    } catch (error) {
      console.error('恢复会话失败:', error);
    }
  },
}));
