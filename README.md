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
| **mc-admin-mod** | Java 21 / NeoForge (MC 1.21.1) | 服务器侧模组，WebSocket 上报状态、接收并执行指令 |
| **mc-admin-server** | Python 3.11 / FastAPI / SQLite / Redis | 云端后端，AI Agent + 用户权限 + 指令中转 |
| **mc-admin-client** | Expo 54 / React Native / TypeScript | 跨平台客户端（iOS / Android / Web） |
| **mc-admin-ios** | Swift / SwiftUI / Xcode | iOS 原生客户端，替代 React Native 方案 |

## 功能

- **自然语言管理** — 输入"把 Steve 设为管理员"，AI 自动执行 `/op Steve`
- **三级模型路由** — flash（简单操作）→ standard（复杂问题）→ pro（深度分析），按需自动选择或手动指定
- **仅查询模式** — AI 只给建议，不执行任何操作，安全观察
- **实时状态监控** — TPS、CPU 占用、内存使用、在线玩家一目了然
- **多轮对话** — 每服务器保留 50 条历史，支持连续追问
- **三级记忆系统** — 全局记忆、管理员记忆、服务器级记忆，AI 长期记住运维偏好
- **命令缓存** — Redis 缓存相同请求，跳过重复 AI 调用，降低延迟和成本
- **命令安全审核** — AI 执行前自动审核指令安全性
- **用户与权限** — 管理员/用户角色，服务器 owner/admin 权限隔离，审批流程
- **多账号切换** — 客户端支持保存多个账号快速切换
- **快捷操作** — 一键重启、踢人、授权、发公告等常用操作
- **Markdown 渲染** — AI 回复支持富文本格式展示
- **安全机制** — Token 认证、JWT 鉴权、命令白名单、危险操作二次确认

## 快速开始

### 前置要求

- Python 3.11+
- Node.js 18+（Expo 客户端）
- Java 21 + Gradle（模组构建）
- Xcode 15+（iOS 原生客户端，可选）
- Docker & Docker Compose（后端部署，推荐）

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

将构建产物（`build/libs/mcadmin-mod-1.0.1.jar`）放入 MC 服务器的 `mods/` 目录。

### 3. 启动客户端

**Expo 跨平台客户端：**

```bash
cd mc-admin-client
npm install
npm start        # Expo 开发服务器
npm run web      # 浏览器访问
npm run ios      # iOS 模拟器
npm run android  # Android 模拟器
```

**iOS 原生客户端：**

```bash
cd mc-admin-ios
open MCAdmin.xcodeproj
# Xcode 中配置签名后构建到真机或模拟器
```

## 通信协议

模组与云服务器之间通过 WebSocket JSON 通信：

**状态上报**（模组 → 服务器）
```json
{
  "type": "status",
  "data": { "tps": 19.8, "players": ["Steve"], "memory_used_mb": 2048, "cpu_usage": 45.2 }
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
│       ├── StatusReporter.java   # 状态定时上报（TPS/内存/CPU）
│       ├── CommandExecutor.java  # 指令执行（主线程调度）
│       ├── LogCollector.java     # 错误日志拦截
│       └── Config.java           # 配置管理
├── mc-admin-server/         # 云端后端
│   └── app/
│       ├── api/                  # REST API（auth、chat、servers、memory）
│       ├── services/             # AI Agent、命令缓存、命令审核、记忆系统
│       ├── websocket/            # 模组 WS 连接管理
│       ├── models/               # 数据模型
│       └── core/                 # 核心配置
├── mc-admin-client/         # Expo 跨平台客户端
│   └── src/
│       ├── screens/              # 页面（登录、聊天、状态、快捷操作、设置）
│       ├── components/           # 通用组件
│       ├── services/             # API 请求服务
│       └── utils/                # 工具函数
├── mc-admin-ios/            # Swift 原生 iOS 客户端
│   └── MCAdmin/
│       ├── Views/                # SwiftUI 视图
│       ├── ViewModels/           # 视图模型
│       ├── Models/               # 数据模型
│       ├── Services/             # 网络服务
│       └── Utils/                # 工具类
└── CLAUDE.md                # 项目规范文档
```

## 开发路线

- [x] Phase 1 — 最小可用：模组 WS 连接 + 后端指令转发 + 网页端聊天
- [x] Phase 2 — 接入 AI：大模型集成、自然语言→指令、多轮对话、三级模型路由、命令缓存、记忆系统
- [x] Phase 3 — 客户端完善：移动端适配、状态面板、服务器选择/绑定、设置页、用户管理、iOS 原生客户端
- [ ] Phase 4 — 增强功能：自动巡检、异常告警、定时任务、多服务器管理、推送通知

## License

MIT
