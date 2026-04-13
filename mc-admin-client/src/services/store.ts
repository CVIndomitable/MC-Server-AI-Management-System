import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substring(2);
}
import { ServerStatus, ChatMessage, UserServerInfo, ServerInfo } from '../types';
import apiService from '../services/api';
import wsService from '../services/websocket';

const TOKEN_KEY = '@mc_admin_token';
const SERVER_ID_KEY = '@mc_admin_server_id';
const QUERY_ONLY_KEY = '@mc_admin_query_only';

interface AppState {
  // 认证状态
  isAuthenticated: boolean;
  token: string | null;
  serverId: string;
  serverSelected: boolean; // 是否已选择服务器

  // 服务器列表
  myServers: UserServerInfo[];
  unboundServers: ServerInfo[];

  // 服务器状态
  serverStatus: ServerStatus | null;

  // 聊天消息
  chatMessages: ChatMessage[];

  // UI状态
  isLoading: boolean;
  error: string | null;
  wsConnected: boolean;
  queryOnlyMode: boolean; // 仅查询模式

  // WebSocket消息处理器引用
  wsMessageHandler: ((message: any) => void) | null;

  // Actions
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
  setServerId: (id: string) => void;
  selectServer: (id: string) => void;
  fetchMyServers: () => Promise<void>;
  fetchUnboundServers: () => Promise<void>;
  bindServer: (serverId: string) => Promise<{ success: boolean; error?: string }>;
  updateServerStatus: (status: ServerStatus) => void;
  addChatMessage: (message: ChatMessage) => void;
  sendMessage: (content: string) => Promise<void>;
  connectWebSocket: () => void;
  disconnectWebSocket: () => void;
  setError: (error: string | null) => void;
  restoreSession: () => Promise<void>;
  toggleQueryOnlyMode: () => void;
  clearServerSelection: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  isAuthenticated: false,
  token: null,
  serverId: '',
  serverSelected: false,
  myServers: [],
  unboundServers: [],
  serverStatus: null,
  chatMessages: [],
  isLoading: false,
  error: null,
  wsConnected: false,
  queryOnlyMode: false,
  wsMessageHandler: null,

  login: async (username: string, password: string) => {
    set({ isLoading: true, error: null });

    const result = await apiService.login({ username, password });

    if (result.success && result.data) {
      const token = result.data.access_token;
      apiService.setToken(token);

      // 持久化token
      await AsyncStorage.setItem(TOKEN_KEY, token);

      set({
        isAuthenticated: true,
        token,
        isLoading: false
      });

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
    AsyncStorage.removeItem(SERVER_ID_KEY);

    set({
      isAuthenticated: false,
      token: null,
      serverId: '',
      serverSelected: false,
      myServers: [],
      unboundServers: [],
      chatMessages: [],
      serverStatus: null
    });
  },

  setServerId: (id: string) => {
    set({ serverId: id });
    AsyncStorage.setItem(SERVER_ID_KEY, id);
  },

  selectServer: (id: string) => {
    set({ serverId: id, serverSelected: true, chatMessages: [] });
    AsyncStorage.setItem(SERVER_ID_KEY, id);
  },

  clearServerSelection: () => {
    get().disconnectWebSocket();
    set({ serverId: '', serverSelected: false, chatMessages: [], serverStatus: null });
    AsyncStorage.removeItem(SERVER_ID_KEY);
  },

  fetchMyServers: async () => {
    const result = await apiService.getMyServers();
    if (result.success && result.data) {
      set({ myServers: result.data.servers });
    }
  },

  fetchUnboundServers: async () => {
    const result = await apiService.getUnboundServers();
    if (result.success && result.data) {
      set({ unboundServers: result.data.servers });
    }
  },

  bindServer: async (serverId: string) => {
    const result = await apiService.bindServer(serverId);
    if (result.success) {
      // 绑定成功，刷新列表
      await get().fetchMyServers();
      return { success: true };
    }
    return { success: false, error: result.error };
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
    const { serverId, token, addChatMessage, queryOnlyMode } = get();

    // 添加用户消息
    const userMessage: ChatMessage = {
      id: generateId(),
      role: 'user',
      content,
      timestamp: Date.now(),
    };
    addChatMessage(userMessage);

    set({ isLoading: true });

    const result = await apiService.sendChatMessage(content, serverId, queryOnlyMode);

    if (result.success && result.data) {
      const aiMessage: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: result.data.message,
        timestamp: Date.now(),
      };
      addChatMessage(aiMessage);
    } else {
      // 添加错误消息
      const errorMessage: ChatMessage = {
        id: generateId(),
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
          id: generateId(),
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
      const queryOnly = await AsyncStorage.getItem(QUERY_ONLY_KEY);

      if (token) {
        apiService.setToken(token);
        set({
          isAuthenticated: true,
          token,
          serverId: serverId || '',
          serverSelected: !!serverId,
          queryOnlyMode: queryOnly === 'true',
        });
      }
    } catch (error) {
      console.error('恢复会话失败:', error);
    }
  },

  toggleQueryOnlyMode: () => {
    const newValue = !get().queryOnlyMode;
    set({ queryOnlyMode: newValue });
    AsyncStorage.setItem(QUERY_ONLY_KEY, String(newValue));
  },
}));
