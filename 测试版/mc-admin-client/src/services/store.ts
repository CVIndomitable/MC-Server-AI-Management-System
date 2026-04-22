import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substring(2);
}
import { ServerStatus, ChatMessage, UserServerInfo, ServerInfo, ModelTier, SavedAccount, WSMessage } from '../types';
import apiService, { setOnUnauthorized } from '../services/api';
import wsService from '../services/websocket';

const TOKEN_KEY = '@mc_admin_token';
const SERVER_ID_KEY = '@mc_admin_server_id';
const QUERY_ONLY_KEY = '@mc_admin_query_only';
const USERNAME_KEY = '@mc_admin_username';
const ROLE_KEY = '@mc_admin_role';
const MODEL_TIER_KEY = '@mc_admin_model_tier';
const SAVED_ACCOUNTS_KEY = '@mc_admin_saved_accounts';
const SAVED_TOKEN_PREFIX = '@mc_admin_token_';
const SHOW_ACTIONS_TAB_KEY = '@mc_admin_show_actions_tab';

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

function parseJwtPayload(token: string): { sub?: string; role?: string; exp?: number } | null {
  try {
    const payload = token.split('.')[1];
    const decoded = base64Decode(payload);
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

function isTokenExpired(token: string): boolean {
  const payload = parseJwtPayload(token);
  if (!payload?.exp) return true;
  // 提前60秒判定过期，留出余量
  return Date.now() / 1000 >= payload.exp - 60;
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
  showActionsTab: boolean;

  // 多账号
  savedAccounts: SavedAccount[];

  // WebSocket处理器引用
  wsMessageHandler: ((message: WSMessage) => void) | null;
  wsStatusHandler: ((connected: boolean) => void) | null;

  // Actions
  login: (username: string, password: string) => Promise<boolean>;
  quickLogin: (username: string) => Promise<boolean>;
  logout: () => Promise<void>;
  loadSavedAccounts: () => Promise<void>;
  removeSavedAccount: (username: string) => Promise<void>;
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
  toggleActionsTab: () => void;
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
  showActionsTab: false,
  savedAccounts: [],
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

      // 保存账号到已保存列表（存储token而非密码）
      try {
        const raw = await AsyncStorage.getItem(SAVED_ACCOUNTS_KEY);
        const accounts: SavedAccount[] = raw ? JSON.parse(raw) : [];
        const existing = accounts.findIndex(a => a.username === parsedUsername);
        if (existing >= 0) {
          accounts[existing].lastUsed = Date.now();
        } else {
          accounts.push({ username: parsedUsername, lastUsed: Date.now() });
        }
        await AsyncStorage.setItem(SAVED_ACCOUNTS_KEY, JSON.stringify(accounts));
        await SecureStore.setItemAsync(SAVED_TOKEN_PREFIX + parsedUsername, token);
      } catch {}
      try {
        const raw = await AsyncStorage.getItem(SAVED_ACCOUNTS_KEY);
        const accounts: SavedAccount[] = raw ? JSON.parse(raw) : [];
        set({ savedAccounts: accounts.sort((a, b) => b.lastUsed - a.lastUsed) });
      } catch {}

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

  quickLogin: async (username: string) => {
    try {
      const savedToken = await SecureStore.getItemAsync(SAVED_TOKEN_PREFIX + username);
      if (!savedToken) return false;

      // 检查token是否过期
      if (isTokenExpired(savedToken)) {
        // token已过期，清理保存的数据
        await SecureStore.deleteItemAsync(SAVED_TOKEN_PREFIX + username);
        return false;
      }

      // token未过期，直接使用
      apiService.setToken(savedToken);
      const payload = parseJwtPayload(savedToken);
      const parsedUsername = payload?.sub || username;
      const parsedRole = payload?.role || 'user';

      await SecureStore.setItemAsync(TOKEN_KEY, savedToken);
      await AsyncStorage.setItem(USERNAME_KEY, parsedUsername);
      await AsyncStorage.setItem(ROLE_KEY, parsedRole);

      // 更新最后使用时间
      try {
        const raw = await AsyncStorage.getItem(SAVED_ACCOUNTS_KEY);
        const accounts: SavedAccount[] = raw ? JSON.parse(raw) : [];
        const existing = accounts.findIndex(a => a.username === parsedUsername);
        if (existing >= 0) {
          accounts[existing].lastUsed = Date.now();
          await AsyncStorage.setItem(SAVED_ACCOUNTS_KEY, JSON.stringify(accounts));
          set({ savedAccounts: accounts.sort((a, b) => b.lastUsed - a.lastUsed) });
        }
      } catch {}

      set({
        isAuthenticated: true,
        token: savedToken,
        username: parsedUsername,
        userRole: parsedRole,
        isLoading: false,
      });
      return true;
    } catch {
      return false;
    }
  },

  loadSavedAccounts: async () => {
    try {
      const raw = await AsyncStorage.getItem(SAVED_ACCOUNTS_KEY);
      if (raw) {
        const accounts: SavedAccount[] = JSON.parse(raw);
        set({ savedAccounts: accounts.sort((a, b) => b.lastUsed - a.lastUsed) });
      }
    } catch {}
  },

  removeSavedAccount: async (username: string) => {
    try {
      const raw = await AsyncStorage.getItem(SAVED_ACCOUNTS_KEY);
      const accounts: SavedAccount[] = raw ? JSON.parse(raw) : [];
      const filtered = accounts.filter(a => a.username !== username);
      await AsyncStorage.setItem(SAVED_ACCOUNTS_KEY, JSON.stringify(filtered));
      await SecureStore.deleteItemAsync(SAVED_TOKEN_PREFIX + username);
      set({ savedAccounts: filtered.sort((a, b) => b.lastUsed - a.lastUsed) });
    } catch {}
  },

  logout: async () => {
    get().disconnectWebSocket();
    apiService.clearToken();

    await Promise.all([
      SecureStore.deleteItemAsync(TOKEN_KEY).catch(() => {}),
      AsyncStorage.removeItem(SERVER_ID_KEY).catch(() => {}),
      AsyncStorage.removeItem(USERNAME_KEY).catch(() => {}),
      AsyncStorage.removeItem(ROLE_KEY).catch(() => {}),
    ]);

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
      if (result.data.degraded && result.data.degraded_message) {
        const noticeMessage: ChatMessage = {
          id: generateId(),
          role: 'assistant',
          content: `[提示] ${result.data.degraded_message}`,
          timestamp: Date.now(),
        };
        addChatMessage(noticeMessage);
      }
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

    const handler = (message: WSMessage) => {
      // 过滤非当前服务器的消息，防止切换服务器时旧消息窜入
      const currentServerId = get().serverId;
      if ('server_id' in message && message.server_id && message.server_id !== currentServerId) return;

      if (message.type === 'status' && message.data) {
        updateServerStatus(message.data);
      } else if (message.type === 'chat_response' && message.message) {
        const chatMsg: ChatMessage = {
          id: generateId(),
          role: 'assistant',
          content: message.message,
          timestamp: Date.now(),
        };
        addChatMessage(chatMsg);
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
      const [token, serverId, queryOnly, username, role, modelTier, showActions] = await Promise.all([
        SecureStore.getItemAsync(TOKEN_KEY).catch(() => null),
        AsyncStorage.getItem(SERVER_ID_KEY).catch(() => null),
        AsyncStorage.getItem(QUERY_ONLY_KEY).catch(() => null),
        AsyncStorage.getItem(USERNAME_KEY).catch(() => null),
        AsyncStorage.getItem(ROLE_KEY).catch(() => null),
        AsyncStorage.getItem(MODEL_TIER_KEY).catch(() => null),
        AsyncStorage.getItem(SHOW_ACTIONS_TAB_KEY).catch(() => null),
      ]);

      // 注入401全局登出回调
      setOnUnauthorized(() => {
        get().logout();
      });

      if (token) {
        // 检查token是否过期
        if (isTokenExpired(token)) {
          await get().logout();
          return;
        }

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
          showActionsTab: showActions === 'true',
        });
      }
    } catch (error) {
      console.warn('恢复会话失败:', error);
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

  toggleActionsTab: () => {
    const newValue = !get().showActionsTab;
    set({ showActionsTab: newValue });
    AsyncStorage.setItem(SHOW_ACTIONS_TAB_KEY, String(newValue));
  },

  getCurrentServerRole: () => {
    const { myServers, serverId } = get();
    const server = myServers.find(s => s.server_id === serverId);
    return server?.role || null;
  },
}));
