import { CONFIG } from '../utils/config';
import { WSMessage } from '../types';

type MessageHandler = (message: WSMessage) => void;
type ConnectionStatusHandler = (connected: boolean) => void;

class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private messageHandlers: Set<MessageHandler> = new Set();
  private statusHandlers: Set<ConnectionStatusHandler> = new Set();
  private isIntentionallyClosed = false;

  connect(token: string, serverId: string) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    this.isIntentionallyClosed = false;
    const wsUrl = CONFIG.wsUrl;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('WebSocket连接成功，发送认证信息');
        // 连接后发送认证消息
        this.send({
          type: 'auth',
          token,
          server_id: serverId,
        } as any);
        this.reconnectAttempts = 0;
        this.notifyStatusHandlers(true);
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WSMessage = JSON.parse(event.data);
          this.notifyHandlers(message);
        } catch (error) {
          console.error('解析WebSocket消息失败:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket错误:', error);
      };

      this.ws.onclose = () => {
        console.log('WebSocket连接关闭');
        this.ws = null;
        this.notifyStatusHandlers(false);

        if (!this.isIntentionallyClosed) {
          this.scheduleReconnect(token, serverId);
        }
      };
    } catch (error) {
      console.error('WebSocket连接失败:', error);
      this.scheduleReconnect(token, serverId);
    }
  }

  private scheduleReconnect(token: string, serverId: string) {
    if (this.reconnectAttempts >= CONFIG.maxReconnectAttempts) {
      console.error('达到最大重连次数，停止重连');
      return;
    }

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    this.reconnectAttempts++;
    const delay = CONFIG.reconnectInterval * Math.min(this.reconnectAttempts, 5);

    console.log(`${delay}ms后尝试第${this.reconnectAttempts}次重连...`);

    this.reconnectTimer = setTimeout(() => {
      this.connect(token, serverId);
    }, delay);
  }

  disconnect() {
    this.isIntentionallyClosed = true;

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.reconnectAttempts = 0;
    this.notifyStatusHandlers(false);
  }

  send(message: WSMessage) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.error('WebSocket未连接，无法发送消息');
    }
  }

  addMessageHandler(handler: MessageHandler) {
    this.messageHandlers.add(handler);
  }

  removeMessageHandler(handler: MessageHandler) {
    this.messageHandlers.delete(handler);
  }

  addStatusHandler(handler: ConnectionStatusHandler) {
    this.statusHandlers.add(handler);
  }

  removeStatusHandler(handler: ConnectionStatusHandler) {
    this.statusHandlers.delete(handler);
  }

  private notifyHandlers(message: WSMessage) {
    this.messageHandlers.forEach(handler => {
      try {
        handler(message);
      } catch (error) {
        console.error('消息处理器执行失败:', error);
      }
    });
  }

  private notifyStatusHandlers(connected: boolean) {
    this.statusHandlers.forEach(handler => {
      try {
        handler(connected);
      } catch (error) {
        console.error('状态处理器执行失败:', error);
      }
    });
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export default new WebSocketService();
