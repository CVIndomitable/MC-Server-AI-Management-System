# MC Admin Client

Minecraft服务器AI管理客户端 - 基于React Native + Expo开发的跨平台应用

## 功能特性

- 💬 **AI对话** - 自然语言控制服务器
- 📊 **实时监控** - TPS、内存、玩家状态
- ⚡ **快捷操作** - 重启、备份、公告等常用功能
- 🔄 **WebSocket** - 实时双向通信
- 📱 **跨平台** - iOS、Android、Web统一代码

## 技术栈

- React Native 0.73
- Expo 50
- TypeScript
- Zustand (状态管理)
- React Navigation
- Axios

## 快速开始

### 安装依赖

```bash
npm install
# 或
yarn install
```

### 配置环境变量

创建 `.env` 文件：

```env
EXPO_PUBLIC_API_URL=http://your-server:8000
EXPO_PUBLIC_WS_URL=ws://your-server:8000/ws
```

### 运行开发服务器

```bash
# Web版
npm run web

# iOS模拟器
npm run ios

# Android模拟器
npm run android

# 启动Expo开发服务器
npm start
```

## 项目结构

```
mc-admin-client/
├── src/
│   ├── components/      # 可复用组件
│   ├── screens/         # 页面组件
│   │   ├── LoginScreen.tsx
│   │   ├── ChatScreen.tsx
│   │   ├── StatusScreen.tsx
│   │   └── ActionsScreen.tsx
│   ├── services/        # 业务逻辑
│   │   ├── api.ts       # REST API
│   │   ├── websocket.ts # WebSocket连接
│   │   └── store.ts     # 状态管理
│   ├── types/           # TypeScript类型定义
│   └── utils/           # 工具函数
├── App.tsx              # 应用入口
├── app.json             # Expo配置
└── package.json
```

## 核心功能

### 1. 认证登录

用户通过用户名密码登录，获取JWT token用于后续API调用和WebSocket连接。

### 2. AI对话

通过聊天界面发送自然语言指令，AI解析后执行相应操作并返回结果。

### 3. 状态监控

实时显示：
- TPS（每秒Tick数）
- 内存使用情况
- 在线玩家列表
- 最近错误日志

### 4. 快捷操作

预设常用操作按钮：
- 重启服务器
- 立即备份
- 发送公告
- 白名单管理
- 停止服务器
- 保存世界

## API接口

客户端与后端通信协议：

### REST API

- `POST /api/v1/auth/login` - 用户登录
- `POST /api/v1/chat` - 发送聊天消息
- `GET /api/v1/servers/:id/status` - 获取服务器状态
- `POST /api/v1/servers/:id/actions` - 执行快捷操作

### WebSocket

连接URL: `ws://server/ws?token=xxx&server_id=xxx`

消息格式：
```json
{
  "type": "status|command|result|chat_response",
  "data": {...}
}
```

## 构建发布

### Web版

```bash
npm run web
# 构建产物在 web-build/ 目录
```

### 移动端

```bash
# 使用EAS Build
eas build --platform ios
eas build --platform android
```

## 注意事项

- 生产环境必须使用HTTPS和WSS协议
- Token需要安全存储（考虑使用SecureStore）
- WebSocket断线会自动重连，最多尝试10次
- 所有时间戳使用Unix时间戳（秒）

## 后续优化

- [ ] 添加推送通知
- [ ] 支持多服务器切换
- [ ] 历史记录持久化
- [ ] 性能图表（TPS/内存趋势）
- [ ] 深色/浅色主题切换
- [ ] 国际化支持

## License

MIT
