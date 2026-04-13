// 配置文件 - 生产环境应从环境变量读取
export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://47.113.221.26/mc-admin';
export const WS_URL = process.env.EXPO_PUBLIC_WS_URL || 'ws://47.113.221.26/mc-admin/ws';

export const CONFIG = {
  apiBaseUrl: API_BASE_URL,
  wsUrl: WS_URL,
  reconnectInterval: 5000, // WebSocket重连间隔(ms)
  statusUpdateInterval: 3000, // 状态更新间隔(ms)
  maxReconnectAttempts: 10,
};
