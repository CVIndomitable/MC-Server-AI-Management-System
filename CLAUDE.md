# CLAUDE.md — MC Server AI Management System

## 项目概述

AI辅助Minecraft服务器管理系统，由三个子项目组成：
- **mc-admin-mod** — NeoForge模组（MC服务器侧执行器）
- **mc-admin-server** — Python FastAPI后端（AI智能体 + 指令中转 + 用户管理）
- **mc-admin-client** — Expo React Native客户端（iOS/Android/Web）

## 架构

```
┌─────────────┐    HTTPS/WS     ┌──────────────────┐    WS(模组主动连出站)    ┌────────────────┐
│  手机/网页    │ ◄────────────► │  云服务器后端      │ ◄──────────────────────► │ MC面板服(模组)   │
│  客户端       │                │  AI Agent + API   │                         │ 仅开放MC端口     │
└─────────────┘                 └──────────────────┘                         └────────────────┘
                                        │
                                        │ API调用
                                        ▼
                                  ┌──────────┐
                                  │ 大模型API  │
                                  └──────────┘
```

**关键约束**：面板服只开放一个MC端口，所有管理通信由模组主动出站WebSocket连接云服务器实现。

## 子项目规范

### 1. mc-admin-mod（NeoForge模组）

- **MC版本**：1.21.1，NeoForge 21.1.77
- **语言**：Java 21
- **构建**：Gradle + NeoGradle，产物 `mcadmin-mod-1.0.1.jar`
- **包名**：`com.mcadmin.mod`
- **核心类**：
  - `MCAdminMod` — 模组入口，生命周期管理
  - `WebSocketManager` — 使用Java内置WebSocket API（java.net.http.WebSocket），无外部依赖
  - `StatusReporter` — 每5秒上报TPS、玩家、内存、错误日志
  - `CommandExecutor` — 主线程执行命令（ServerTickEvent调度），含命令白名单
  - `LogCollector` — 拦截WARN/ERROR级别日志
  - `Config` — 配置管理（WS地址、token、server_id）
- **安全**：连接需token认证，指令有权限白名单，危险操作需二次确认
- **注意**：Gson已内置于Minecraft，无需额外打包；ASM版本冲突需force resolution到9.7

### 2. mc-admin-server（云服务器后端）

- **语言**：Python 3.11+（FastAPI + Uvicorn）
- **数据库**：SQLite（用户/服务器持久化）+ Redis 7（命令缓存 + 记忆合并）
- **部署**：Docker Compose（api + redis两个服务），暴露端口8000
- **API路由**：
  - `/api/v1/auth` — 登录、注册（管理员创建）、改密、重置密码、用户CRUD
  - `/api/v1/chat` — AI对话，支持指定模型等级和仅查询模式
  - `/api/v1/servers` — 服务器列表、绑定/解绑、审批申请、重命名、管理员列表
  - `/api/v1/memory` — 三级记忆系统CRUD
  - `/ws/mod` — 模组WebSocket连接端点
- **AI Agent设计**：
  - 通过Anthropic SDK调用大模型，base_url可配置（支持兼容API网关）
  - 三级模型路由：flash（简单操作）→ standard（复杂问题）→ pro（深度分析），按关键词和消息长度自动选择，客户端也可指定
  - Function Calling工具：execute_command, kick_player, op_player, deop_player, get_status, restart_server, broadcast
  - 仅查询模式：AI只给建议，不执行任何操作
  - Redis命令缓存：相同消息跳过大模型调用，LFU淘汰策略，默认1小时TTL
  - 三级长期记忆：全局记忆、管理员记忆、服务器级记忆，注入System Prompt
  - 支持多轮对话，每服务器保留50条历史
- **用户与权限**：
  - SQLite存储用户，bcrypt加密密码，JWT认证（默认7天过期）
  - 系统角色：admin / user
  - 服务器角色：owner（首个绑定者）/ admin（审批加入）
  - 用户-服务器绑定系统，支持权限隔离和审批流程

### 3. mc-admin-client（客户端）

- **技术栈**：Expo 54 + React Native 0.81 + TypeScript
- **状态管理**：Zustand
- **HTTP客户端**：Axios
- **页面**：
  - `LoginScreen` — 用户登录
  - `ServerSelectScreen` — 服务器选择、绑定、审批待处理申请
  - `ChatScreen` — AI对话界面
  - `StatusScreen` — 实时监控（TPS、内存图表、玩家列表）
  - `ActionsScreen` — 快捷操作按钮
  - `SettingsScreen` — 账号信息、修改密码、服务器管理（重命名/解绑用户）、用户管理（管理员功能：注册/删除/重置密码）
- **平台支持**：iOS、Android、Web（`npm run web`）

## 指令协议（模组 ↔ 云服务器 WebSocket JSON）

### 模组 → 服务器（上报）

```json
{
  "type": "status",
  "server_id": "srv_001",
  "timestamp": 1700000000,
  "data": {
    "tps": 19.8,
    "players": ["Steve", "Alex"],
    "memory_used_mb": 2048,
    "memory_max_mb": 4096,
    "recent_errors": ["[WARN] Can't keep up!"]
  }
}
```

### 服务器 → 模组（指令）

```json
{
  "type": "command",
  "id": "cmd_abc123",
  "action": "execute",
  "payload": {
    "command": "/op Steve"
  }
}
```

### 模组 → 服务器（执行结果）

```json
{
  "type": "result",
  "command_id": "cmd_abc123",
  "success": true,
  "output": "Made Steve a server operator"
}
```

## 开发进度

- **Phase 1 — 最小可用** ✅ 模组WS连接 + 后端指令转发 + 网页端聊天
- **Phase 2 — 接入AI** ✅ 大模型API集成、自然语言→指令转换、多轮对话、三级模型路由、命令缓存、记忆系统
- **Phase 3 — 客户端完善** ✅ 移动端适配、状态面板、服务器选择/绑定、设置页、用户管理
- **Phase 4 — 增强功能**（待开发）：自动巡检、异常告警、定时任务、多服务器管理、推送通知

## 编码约定

- 模组代码遵循Mojang/NeoForge命名风格，包名 `com.mcadmin.mod`
- 后端API遵循RESTful，路径 `/api/v1/...`
- 所有通信JSON格式，UTF-8编码
- 敏感配置（token、API key）走环境变量 `.env`，不硬编码
- 中文注释优先，公开API英文命名

## 注意事项

- 面板服出站连接能力需实际验证，如果不通则回退到HTTP轮询方案
- 大模型选择灵活，base_url可配置，支持任何兼容Anthropic API的网关
- 模组侧命令执行必须在服务器主线程（通过ServerTickEvent调度）
- 客户端↔后端走HTTPS，后端↔模组WS也应加TLS（wss://）
- `docs/` 目录含敏感服务器信息和key，已在 `.gitignore` 中排除，禁止提交
