# CLAUDE.md — MC Server AI Management System

## 项目概述

AI辅助Minecraft服务器管理系统，由三个子项目组成：
- **mc-admin-mod** — Minecraft Forge模组（服务器侧执行器）
- **mc-admin-server** — 云服务器后端（AI智能体 + 指令中转）
- **mc-admin-client** — 手机/网页客户端（用户交互界面）

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

### 1. mc-admin-mod（Forge模组）

- **MC版本**：1.21.1，Forge/NeoForge（优先NeoForge）
- **语言**：Java 21
- **构建**：Gradle + NeoGradle
- **职责**：
  - 启动时主动WebSocket连接云服务器，断线自动重连
  - 定时上报状态：TPS、在线玩家列表、内存占用、最近日志摘要
  - 接收并执行结构化指令（见指令协议）
  - 回传执行结果和错误信息
- **安全**：连接需token认证，指令有权限白名单，危险操作需二次确认

### 2. mc-admin-server（云服务器后端）

- **语言**：Python 3.11+（FastAPI）或 Node.js（待定）
- **职责**：
  - 提供REST API给客户端（认证、对话、状态查询）
  - 维护与模组的WebSocket长连接
  - 调用大模型API，将自然语言解析为结构化指令
  - 缓存服务器状态，维护指令队列和执行历史
  - 用户认证与权限管理
- **AI Agent设计**：
  - System Prompt定义角色为MC服务器管理员
  - 提供工具/函数：execute_command, kick_player, op_player, get_status, get_logs, restart_server等
  - 大模型通过function calling选择工具，后端翻译为指令发给模组
  - 支持多轮对话，保留上下文
- **部署**：低配云服务器（1核1G足够），Docker部署

### 3. mc-admin-client（客户端）

- **技术栈**：React Native（iOS+Android）+ 同一代码库出Web版，或Flutter
- **功能**：
  - 聊天界面：自然语言描述问题，AI回复处理结果
  - 状态面板：实时TPS、玩家列表、内存图表
  - 快捷操作按钮：重启、备份、公告等常用功能
  - 通知推送：服务器异常时主动通知

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

## 开发顺序

1. **Phase 1 — 最小可用**：模组WS连接 + 后端指令转发 + 网页端聊天（跳过AI，手动发指令验证链路）
2. **Phase 2 — 接入AI**：后端接大模型API，自然语言→指令转换，多轮对话
3. **Phase 3 — 客户端完善**：React Native移动端，状态面板，推送通知
4. **Phase 4 — 增强功能**：自动巡检、异常告警、定时任务、多服务器管理

## 编码约定

- 模组代码遵循Mojang/NeoForge命名风格，包名 `com.example.mcadmin`（后续替换）
- 后端API遵循RESTful，路径 `/api/v1/...`
- 所有通信JSON格式，UTF-8编码
- 敏感配置（token、API key）走环境变量或配置文件，不硬编码
- 中文注释优先，公开API英文命名

## 注意事项

- 面板服出站连接能力需实际验证，如果不通则回退到HTTP轮询方案
- 大模型选择灵活，预留provider抽象层，不绑死某家API
- 模组侧命令执行必须在服务器主线程（通过ServerTickEvent调度）
- 客户端↔后端走HTTPS，后端↔模组WS也应加TLS（wss://）
