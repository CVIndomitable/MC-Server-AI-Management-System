# CLAUDE.md — MC Server AI Management System

## 项目概述

AI辅助Minecraft服务器管理系统，三个子项目：
- **mc-admin-mod** — NeoForge模组（MC服务器侧执行器，Java 21 / MC 1.21.1 / NeoForge 21.1.77）
- **mc-admin-server** — Python FastAPI后端（AI智能体 + 指令中转 + 用户管理）
- **mc-admin-client** — Expo React Native客户端（iOS/Android/Web）
- **mc-admin-ios** — Swift 原生 iOS 客户端（"构建到手机"默认指此版）

## 架构

```
┌─────────────┐    HTTPS/WS     ┌──────────────────┐    WS(模组主动出站)     ┌────────────────┐
│  手机/网页    │ ◄────────────► │  云服务器后端      │ ◄──────────────────────► │ MC面板服(模组)   │
│  客户端       │                │  AI Agent + API   │                         │ 仅开放MC端口     │
└─────────────┘                 └──────────────────┘                         └────────────────┘
                                        │ 调用大模型API
                                        ▼
```

**关键约束**：面板服只开放MC端口，所有管理通信由模组主动出站WebSocket连接云服务器实现。

## 详细规范

子项目类设计、API 路由、AI Agent、WebSocket 协议 JSON 示例、开发进度等详见 [`README.md`](README.md) 的「详细规范」与「通信协议」章节。

## 编码约定

- 模组代码遵循Mojang/NeoForge命名风格，包名 `com.mcadmin.mod`
- 后端API遵循RESTful，路径 `/api/v1/...`
- 所有通信JSON格式，UTF-8编码
- 敏感配置（token、API key）走环境变量 `.env`，不硬编码
- 中文注释优先，公开API英文命名

## 注意事项

- 面板服出站连接能力需实际验证，如果不通则回退到HTTP轮询方案
- 大模型 base_url 可配置，支持任何兼容 Anthropic API 的网关
- 模组侧命令执行必须在服务器主线程（通过ServerTickEvent调度）
- 客户端↔后端走HTTPS，后端↔模组WS也应加TLS（wss://）
- `docs/` 目录含敏感服务器信息和key，已在 `.gitignore` 中排除，禁止提交
