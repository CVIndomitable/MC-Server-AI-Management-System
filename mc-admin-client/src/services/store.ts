import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substring(2);
}
import { ServerStatus, ChatMessage, UserServerInfo, ServerInfo, ModelTier } from '../types';
import apiService from '../services/api';
import wsService from '../services/websocket';

const TOKEN_KEY = '@mc_admin_token';
const SERVER_ID_KEY = '@mc_admin_server_id';
const QUERY_ONLY_KEY = '@mc_admin_query_only';
const USERNAME_KEY = '@mc_admin_username';
const ROLE_KEY = '@mc_admin_role';
const MODEL_TIER_KEY = '@mc_admin_model_tier';

// 从JWT中解析payload（兼容无atob的环境）
function base64Decode(str: string): string {
  const base64 = str.replace(/-/g, '+').replace(/_/g, '/');
  const padded = base64 + '='.repeat((4 - base64.length % 4) % 4);
  if (typeof atob !== 'undefined') return atob(padded);
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  let result = '', bits = 0, buffer = 0;
  for (const c of padded) {
    if (c === '=') break;
    buffer = (buffer << 6) | chars.indexOf(c);
    bits += 6;
    if (bits >= 8) { bits -= 8; result += String.fromCharCode((buffer >> bits) & 0xFF); }
  }
  return result;
}

function parseJwtPayload(token: string): { sub?: string; role?: string } | null {
  try {
    const payload = token.split('.')[1];
    const decoded = base64Decode(payload);
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

interface AppState {
  // 认证状态
  isAuthenticated: boolean;
  token: string | null;
  username: string;
  userRole: string; // admin | user
  serverId: string;
  serverSelected: boolean;

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
  queryOnlyMode: boolean;
  modelTier: ModelTier | undefined;

  // WebSocket处理器引用
  wsMessageHandler: ((message: any) => void) | null;
  wsStatusHandler: ((connected: boolean) => void) | null;

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
  setModelTier: (tier: ModelTier | undefined) => void;
  clearServerSelection: () => void;
  getCurrentServerRole: () => string | null;
}

export const useAppStore = create<AppState>((set, get) => ({
  isAuthenticated: false,
  token: null,
  username: '',
  userRole: '',
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
  modelTier: undefined,
  wsMessageHandler: null,
  wsStatusHandler: null,

  login: async (username: string, password: string) => {
    set({ isLoading: true, error: null });

    const result = await apiService.login({ username, password });

    if (result.success && result.data) {
      const token = result.data.access_token;
      apiService.setToken(token);

      // 从JWT解析用户信息
      const payload = parseJwtPayload(token);
      const parsedUsername = payload?.sub || username;
      const parsedRole = payload?.role || 'user';

      await SecureStore.setItemAsync(TOKEN_KEY, token);
      await AsyncStorage.setItem(USERNAME_KEY, parsedUsername);
      await AsyncStorage.setItem(ROLE_KEY, parsedRole);

      set({
        isAuthenticated: true,
        token,
        username: parsedUsername,
        userRole: parsedRole,
        isLoading: false,
      });

      return true;
    } else {
      set({
        isLoading: false,
        error: result.error || '登录失败',
      });
      return false;
    }
  },

  logout: () => {
    get().disconnectWebSocket();
    apiService.clearToken();

    SecureStore.deleteItemAsync(TOKEN_KEY);
    AsyncStorage.removeItem(SERVER_ID_KEY);
    AsyncStorage.removeItem(USERNAME_KEY);
    AsyncStorage.removeItem(ROLE_KEY);

    set({
      isAuthenticated: false,
      token: null,
      username: '',
      userRole: '',
      serverId: '',
      serverSelected: false,
      myServers: [],
      unboundServers: [],
      chatMessages: [],
      serverStatus: null,
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
      await get().fetchMyServers();
      return { success: true };
    }
    return { success: false, error: result.error };
  },

  updateServerStatus: (status: ServerStatus) => {
    set({ serverStatus: status });
  },

  addChatMessage: (message: ChatMessage) => {
    set(state => {
      const messages = [...state.chatMessages, message];
      return { chatMessages: messages.length > 100 ? messages.slice(-100) : messages };
    });
  },

  sendMessage: async (content: string) => {
    const { serverId, addChatMessage, queryOnlyMode, modelTier } = get();

    const userMessage: ChatMessage = {
      id: generateId(),
      role: 'user',
      content,
      timestamp: Date.now(),
    };
    addChatMessage(userMessage);

    set({ isLoading: true });

    const result = await apiService.sendChatMessage(content, serverId, queryOnlyMode, modelTier);

    if (result.success && result.data) {
      const aiMessage: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: result.data.message,
        timestamp: Date.now(),
        review: result.data.review,
      };
      addChatMessage(aiMessage);
    } else {
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
    const { token, serverId, updateServerStatus, addChatMessage, wsMessageHandler, wsStatusHandler } = get();

    if (!token) return;

    if (wsMessageHandler) {
      wsService.removeMessageHandler(wsMessageHandler);
    }
    if (wsStatusHandler) {
      wsService.removeStatusHandler(wsStatusHandler);
    }

    wsService.connect(token, serverId);

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

    const newStatusHandler = (connected: boolean) => {
      set({ wsConnected: connected });
    };

    wsService.addMessageHandler(handler);
    wsService.addStatusHandler(newStatusHandler);
    set({ wsMessageHandler: handler, wsStatusHandler: newStatusHandler });
  },

  disconnectWebSocket: () => {
    const { wsMessageHandler, wsStatusHandler } = get();

    if (wsMessageHandler) {
      wsService.removeMessageHandler(wsMessageHandler);
    }
    if (wsStatusHandler) {
      wsService.removeStatusHandler(wsStatusHandler);
    }
    set({ wsMessageHandler: null, wsStatusHandler: null });

    wsService.disconnect();
  },

  setError: (error: string | null) => {
    set({ error });
  },

  restoreSession: async () => {
    try {
      const [token, serverId, queryOnly, username, role, modelTier] = await Promise.all([
        SecureStore.getItemAsync(TOKEN_KEY),
        AsyncStorage.getItem(SERVER_ID_KEY),
        AsyncStorage.getItem(QUERY_ONLY_KEY),
        AsyncStorage.getItem(USERNAME_KEY),
        AsyncStorage.getItem(ROLE_KEY),
        AsyncStorage.getItem(MODEL_TIER_KEY),
      ]);

      if (token) {
        apiService.setToken(token);

        // 如果没有缓存的用户名，尝试从JWT解析
        let resolvedUsername = username || '';
        let resolvedRole = role || '';
        if (!resolvedUsername) {
          const payload = parseJwtPayload(token);
          resolvedUsername = payload?.sub || '';
          resolvedRole = payload?.role || '';
        }

        set({
          isAuthenticated: true,
          token,
          username: resolvedUsername,
          userRole: resolvedRole,
          serverId: serverId || '',
          serverSelected: !!serverId,
          queryOnlyMode: queryOnly === 'true',
          modelTier: (modelTier as ModelTier) || undefined,
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

  setModelTier: (tier: ModelTier | undefined) => {
    set({ modelTier: tier });
    if (tier) {
      AsyncStorage.setItem(MODEL_TIER_KEY, tier);
    } else {
      AsyncStorage.removeItem(MODEL_TIER_KEY);
    }
  },

  getCurrentServerRole: () => {
    const { myServers, serverId } = get();
    const server = myServers.find(s => s.server_id === serverId);
    return server?.role || null;
  },
}));
