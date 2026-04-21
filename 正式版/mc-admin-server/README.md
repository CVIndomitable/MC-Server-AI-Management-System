# MC Admin Server

Minecraft服务器AI管理后端，提供REST API和WebSocket连接管理。

## 功能

- **AI智能体**：接入Claude API，自然语言解析为MC指令
- **WebSocket管理**：处理模组主动连接，实时状态上报
- **REST API**：客户端认证、对话、状态查询
- **指令执行**：结构化指令下发与结果回传

## 快速开始

### 1. 环境配置

```bash
cp .env.example .env
# 编辑.env，填入必要的配置
```

必填配置项：
- `SECRET_KEY`：JWT密钥
- `ANTHROPIC_API_KEY`：Claude API密钥
- `MOD_AUTH_TOKEN`：模组连接认证token

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动服务

```bash
python run.py
```

或使用Docker：

```bash
docker-compose up -d
```

## API文档

启动后访问：http://localhost:8000/docs

### 主要接口

**认证**
- `POST /api/v1/auth/login` - 用户登录

**对话**
- `POST /api/v1/chat` - 发送消息给AI
- `GET /api/v1/status/{server_id}` - 获取服务器状态

**WebSocket**
- `WS /ws/mod?server_id=xxx&token=xxx` - 模组连接端点

## 项目结构

```
mc-admin-server/
├── app/
│   ├── api/          # REST API路由
│   ├── core/         # 核心功能（认证等）
│   ├── models/       # 数据模型
│   ├── services/     # 业务逻辑（AI Agent）
│   ├── websocket/    # WebSocket管理
│   └── main.py       # FastAPI应用入口
├── config/           # 配置文件
├── tests/            # 测试
├── requirements.txt  # Python依赖
├── run.py            # 启动脚本
└── docker-compose.yml
```

## 开发

默认用户：`admin` / `admin123`（生产环境请修改）

## 协议

WebSocket消息格式见 CLAUDE.md
