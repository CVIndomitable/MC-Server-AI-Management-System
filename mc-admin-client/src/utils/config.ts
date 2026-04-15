// 配置文件 - 生产环境应通过环境变量配置
const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://47.113.221.26/mc-admin';
const WS_URL = process.env.EXPO_PUBLIC_WS_URL || 'ws://47.113.221.26/mc-admin/ws';

// 启动时校验环境变量
if (!process.env.EXPO_PUBLIC_API_URL) {
  console.warn('[Config] EXPO_PUBLIC_API_URL 未设置，使用默认值。生产环境请通过 .env 配置。');
}
if (!process.env.EXPO_PUBLIC_WS_URL) {
  console.warn('[Config] EXPO_PUBLIC_WS_URL 未设置，使用默认值。生产环境请通过 .env 配置。');
}

export const CONFIG = {
  apiBaseUrl: API_BASE_URL,
  wsUrl: WS_URL,
  reconnectInterval: 5000, // WebSocket重连基础间隔(ms)
  statusUpdateInterval: 3000, // 状态更新间隔(ms)
  maxReconnectAttempts: 10,
};

export { API_BASE_URL, WS_URL };
