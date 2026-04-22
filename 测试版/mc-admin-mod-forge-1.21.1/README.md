# MC Admin Mod

AI辅助Minecraft服务器管理模组（NeoForge 1.21.1）

## 功能

- **WebSocket连接**：模组主动连接云服务器，支持断线重连和token认证
- **状态上报**：每5秒上报TPS、在线玩家、内存占用等服务器状态
- **指令执行**：接收云服务器下发的管理指令，在服务器主线程安全执行
- **安全机制**：命令白名单、权限验证

## 构建

```bash
./gradlew build
```

生成的jar文件位于 `build/libs/mcadmin-mod-1.0.0.jar`

## 安装

1. 将jar文件放入服务器的 `mods/` 目录
2. 复制 `config/mcadmin.properties.example` 为 `config/mcadmin.properties`
3. 修改配置文件中的WebSocket地址和认证token
4. 启动服务器

## 配置

编辑 `config/mcadmin.properties`：

```properties
# WebSocket服务器地址
ws.url=ws://your-server.com:8080/ws

# 认证token
ws.token=your_secret_token

# 服务器唯一标识
server.id=srv_001
```

## 协议

### 状态上报（模组 → 服务器）

```json
{
  "type": "status",
  "server_id": "srv_001",
  "timestamp": 1700000000,
  "data": {
    "tps": 19.8,
    "players": ["Steve", "Alex"],
    "player_count": 2,
    "max_players": 20,
    "memory_used_mb": 2048,
    "memory_max_mb": 4096,
    "recent_errors": ""
  }
}
```

### 指令接收（服务器 → 模组）

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

### 执行结果（模组 → 服务器）

```json
{
  "type": "result",
  "command_id": "cmd_abc123",
  "success": true,
  "output": "Made Steve a server operator"
}
```

## 支持的指令

- `execute` - 执行Minecraft命令（白名单限制）
- `kick_player` - 踢出玩家
- `op_player` - 授予OP权限
- `restart` - 重启服务器

## 开发

需要Java 21和Gradle 8.x

```bash
# 运行开发服务器
./gradlew runServer
```

## 许可

MIT License
