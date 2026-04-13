# MC Server AI Management System

用自然语言管理你的 Minecraft 服务器 —— AI 理解你的意图，自动执行服务器指令。

## 架构

```
┌─────────────┐    HTTPS/WS     ┌──────────────────┐    WS(模组主动出站)     ┌────────────────┐
│  手机/网页    │ ◄────────────► │  云服务器后端      │ ◄──────────────────► │ MC 面板服(模组)  │
│  客户端       │                │  AI Agent + API   │                      │ 仅开放 MC 端口   │
└─────────────┘                 └──────────────────┘                      └────────────────┘
                                        │
                                        ▼
                                   大模型 API
```

面板服只开放一个 MC 端口，所有管理通信由模组主动出站 WebSocket 连接云服务器实现。

## 子项目

| 子项目 | 技术栈 | 说明 |
|--------|--------|------|
| **mc-admin-mod** | Java 21 / NeoForge (MC 1.21.1) | 服务器侧 Forge 模组，WebSocket 上报状态、接收并执行指令 |
| **mc-admin-server** | Python 3.11 / FastAPI / Redis | 云端后端，AI Agent 解析自然语言为结构化指令，中转至模组 |
| **mc-admin-client** | React Native (Expo) / TypeScript | 移动端 + Web 客户端，聊天界面、状态面板、快捷操作 |

## 快速开始

### 前置要求

- Python 3.11+
- Node.js 18+
- Java 21 + Gradle
- Docker & Docker Compose（可选，用于部署后端）
- Redis（后端依赖，Docker Compose 已包含）

### 1. 启动后端

```bash
cd mc-admin-server

# 创建环境变量配置
cp .env.example .env  # 填入 API Key、Token 等

# Docker 方式（推荐）
docker compose up -d

# 或本地运行
pip install -r requirements.txt
python run.py
```

后端默认监听 `http://localhost:8000`。

### 2. 构建模组

```bash
cd mc-admin-mod

# 编辑配置：设置云服务器地址和认证 Token
# config/ 目录下的配置文件

# 构建
./gradlew build
```

将构建产物（`build/libs/mcadmin-mod-1.0.0.jar`）放入 MC 服务器的 `mods/` 目录。

### 3. 启动客户端

```bash
cd mc-admin-client

npm install

# 开发模式
npm start        # Expo 开发服务器
npm run web      # 浏览器访问
npm run ios      # iOS 模拟器
npm run android  # Android 模拟器
```

## 功能

- **自然语言管理** — 输入"把 Steve 设为管理员"，AI 自动执行 `/op Steve`
- **实时状态监控** — TPS、在线玩家、内存占用一目了然
- **快捷操作** — 一键重启、备份、发公告等常用操作
- **多轮对话** — AI 保留上下文，支持连续追问和复杂操作
- **安全机制** — Token 认证、权限白名单、危险操作二次确认

## 通信协议

模组与云服务器之间通过 WebSocket JSON 通信：

**状态上报**（模组 → 服务器）
```json
{
  "type": "status",
  "data": { "tps": 19.8, "players": ["Steve"], "memory_used_mb": 2048 }
}
```

**下发指令**（服务器 → 模组）
```json
{
  "type": "command",
  "id": "cmd_abc123",
  "action": "execute",
  "payload": { "command": "/op Steve" }
}
```

**执行结果**（模组 → 服务器）
```json
{
  "type": "result",
  "command_id": "cmd_abc123",
  "success": true,
  "output": "Made Steve a server operator"
}
```

## 项目结构

```
├── mc-admin-mod/            # Minecraft NeoForge 模组
│   └── src/main/java/com/mcadmin/mod/
│       ├── MCAdminMod.java       # 模组入口
│       ├── WebSocketManager.java # WS 连接管理
│       ├── StatusReporter.java   # 状态定时上报
│       ├── CommandExecutor.java  # 指令执行（主线程调度）
│       └── Config.java           # 配置管理
├── mc-admin-server/         # 云端后端
│   └── app/
│       ├── api/                  # REST API（auth、chat）
│       ├── services/             # AI Agent 服务
│       ├── websocket/            # 模组 WS 连接管理
│       ├── models/               # 数据模型
│       └── core/                 # 核心配置
├── mc-admin-client/         # 移动端 + Web 客户端
│   └── src/
│       ├── screens/              # 页面（登录、聊天、状态、快捷操作）
│       ├── components/           # 通用组件
│       ├── services/             # API 请求服务
│       └── utils/                # 工具函数
└── CLAUDE.md                # 项目规范文档
```

## 开发路线

- [x] Phase 1 — 最小可用：模组 WS 连接 + 后端指令转发 + 网页端聊天
- [ ] Phase 2 — 接入 AI：自然语言 → 指令转换，多轮对话
- [ ] Phase 3 — 客户端完善：移动端优化，状态面板，推送通知
- [ ] Phase 4 — 增强功能：自动巡检、异常告警、定时任务、多服务器管理

## License

MIT
