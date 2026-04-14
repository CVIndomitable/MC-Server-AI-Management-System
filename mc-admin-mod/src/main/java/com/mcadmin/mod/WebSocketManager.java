package com.mcadmin.mod;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class WebSocketManager {
    private static final Logger LOGGER = LoggerFactory.getLogger(WebSocketManager.class);
    private static final long INITIAL_RECONNECT_DELAY = 5000;
    private static final long MAX_RECONNECT_DELAY = 60000;
    private static final long HEARTBEAT_INTERVAL = 30000;
    private static final int MAX_MESSAGE_SIZE = 1024 * 1024; // 1MB消息大小限制

    private volatile WebSocket webSocket;
    private final CommandExecutor commandExecutor;
    private final StatusReporter statusReporter;
    private final AtomicBoolean shouldReconnect = new AtomicBoolean(true);
    private final AtomicBoolean connected = new AtomicBoolean(false);
    private final HttpClient httpClient;
    private volatile long currentReconnectDelay = INITIAL_RECONNECT_DELAY;

    // 用 ScheduledExecutorService 代替 Timer，避免资源泄漏
    private final ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "MCAdmin-Scheduler");
            t.setDaemon(true);
            return t;
        });
    private volatile ScheduledFuture<?> reconnectFuture;
    private volatile ScheduledFuture<?> heartbeatFuture;

    // 待确认命令追踪，防止伪造 confirmed=true 绕过确认
    private final Set<String> pendingConfirmations = ConcurrentHashMap.newKeySet();

    public WebSocketManager(CommandExecutor commandExecutor, StatusReporter statusReporter) {
        this.commandExecutor = commandExecutor;
        this.statusReporter = statusReporter;
        this.httpClient = HttpClient.newHttpClient();
    }

    public void connect() {
        try {
            String wsUrl = Config.getWsUrl();
            String authToken = Config.getAuthToken();
            String serverId = Config.getServerId();

            // Token通过Header传输（不暴露在URL中）
            LOGGER.info("Connecting to WebSocket: {}", wsUrl);

            httpClient.newWebSocketBuilder()
                .header("Authorization", "Bearer " + authToken)
                .header("X-Server-Id", serverId)
                .buildAsync(URI.create(wsUrl), new WebSocket.Listener() {
                    private final StringBuilder messageBuffer = new StringBuilder();

                    @Override
                    public void onOpen(WebSocket ws) {
                        LOGGER.info("WebSocket connected to {}", wsUrl);
                        webSocket = ws;
                        connected.set(true);
                        currentReconnectDelay = INITIAL_RECONNECT_DELAY;
                        startHeartbeat();
                        ws.request(1);
                    }

                    @Override
                    public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
                        // 消息大小限制，防止OOM
                        if (messageBuffer.length() + data.length() > MAX_MESSAGE_SIZE) {
                            LOGGER.warn("Message exceeds max size ({}), discarding", MAX_MESSAGE_SIZE);
                            messageBuffer.setLength(0);
                            ws.request(1);
                            return null;
                        }
                        messageBuffer.append(data);
                        if (last) {
                            String message = messageBuffer.toString();
                            messageBuffer.setLength(0);
                            handleMessage(message);
                        }
                        ws.request(1);
                        return null;
                    }

                    @Override
                    public CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason) {
                        LOGGER.warn("WebSocket closed: {} - {}", statusCode, reason);
                        connected.set(false);
                        webSocket = null;
                        stopHeartbeat();
                        scheduleReconnect();
                        return null;
                    }

                    @Override
                    public void onError(WebSocket ws, Throwable error) {
                        LOGGER.error("WebSocket error: {}", error.getMessage());
                        connected.set(false);
                        webSocket = null;
                        stopHeartbeat();
                        scheduleReconnect();
                    }
                })
                .exceptionally(ex -> {
                    LOGGER.error("Failed to connect WebSocket: {}", ex.getMessage());
                    scheduleReconnect();
                    return null;
                });
        } catch (Exception e) {
            LOGGER.error("Failed to initiate WebSocket connection", e);
            scheduleReconnect();
        }
    }

    private void handleMessage(String message) {
        try {
            JsonObject json = JsonParser.parseString(message).getAsJsonObject();
            if (!json.has("type") || json.get("type").isJsonNull()) {
                LOGGER.warn("Invalid message: missing 'type' field");
                return;
            }
            String type = json.get("type").getAsString();

            switch (type) {
                case "command":
                    handleCommand(json);
                    break;
                case "update_whitelist":
                    handleWhitelistUpdate(json);
                    break;
                case "auth_response":
                    LOGGER.debug("Received auth_response");
                    break;
                case "pong":
                    break;
                default:
                    LOGGER.warn("Unknown message type: {}", type);
            }
        } catch (Exception e) {
            LOGGER.error("Failed to handle message: {}", message, e);
        }
    }

    private void handleCommand(JsonObject json) {
        // 安全的JSON字段访问，防止NullPointerException
        if (!json.has("id") || json.get("id").isJsonNull()
                || !json.has("action") || json.get("action").isJsonNull()) {
            LOGGER.warn("Invalid command message: missing 'id' or 'action'");
            return;
        }

        String commandId = json.get("id").getAsString();
        String action = json.get("action").getAsString();
        JsonObject payload = json.has("payload") && !json.get("payload").isJsonNull()
            ? json.getAsJsonObject("payload") : new JsonObject();

        // 提取扩展字段
        String adminId = payload.has("admin_id") && !payload.get("admin_id").isJsonNull()
            ? payload.get("admin_id").getAsString() : null;
        boolean confirmed = payload.has("confirmed") && payload.get("confirmed").getAsBoolean();

        LOGGER.info("Received command: {} ({}) from admin: {}", action, commandId,
            adminId != null ? adminId : "unknown");

        // 二次确认检查：危险操作 + 开启确认 + 未确认 → 拒绝并要求确认
        if (Config.requireConfirmation() && !confirmed
                && commandExecutor.isDangerousAction(action, payload)) {
            String detail = commandExecutor.describeCommand(action, payload);
            LOGGER.warn("Dangerous command requires confirmation: {} ({})", detail, commandId);
            pendingConfirmations.add(commandId);
            sendConfirmRequired(commandId, action, detail, adminId);
            return;
        }

        // 如果标记了 confirmed，必须是之前请求过确认的命令
        if (confirmed && Config.requireConfirmation()) {
            if (!pendingConfirmations.remove(commandId)) {
                LOGGER.warn("Received confirmed command {} that was not pending confirmation, rejecting", commandId);
                sendCommandResult(commandId, false, "Command was not pending confirmation", adminId);
                return;
            }
        }

        commandExecutor.executeCommand(commandId, action, payload, (success, output) -> {
            sendCommandResult(commandId, success, output, adminId);
        });
    }

    /**
     * 处理服务器下发的白名单更新
     * 消息格式: {"type": "update_whitelist", "commands": ["list", "say", ...]}
     */
    private void handleWhitelistUpdate(JsonObject json) {
        if (!json.has("commands") || json.get("commands").isJsonNull()) {
            LOGGER.warn("Invalid update_whitelist message: missing 'commands' field");
            return;
        }

        JsonArray commandsArray = json.getAsJsonArray("commands");
        Set<String> newCommands = new HashSet<>();
        for (int i = 0; i < commandsArray.size(); i++) {
            newCommands.add(commandsArray.get(i).getAsString());
        }

        commandExecutor.updateAllowedCommands(newCommands);
        LOGGER.info("Command whitelist updated from server: {} commands", newCommands.size());
    }

    /**
     * 发送二次确认请求
     */
    private void sendConfirmRequired(String commandId, String action, String detail, String adminId) {
        JsonObject msg = new JsonObject();
        msg.addProperty("type", "confirm_required");
        msg.addProperty("command_id", commandId);
        msg.addProperty("action", action);
        msg.addProperty("detail", detail);
        msg.addProperty("server_id", Config.getServerId());
        msg.addProperty("timestamp", System.currentTimeMillis() / 1000);
        if (adminId != null) {
            msg.addProperty("admin_id", adminId);
        }
        sendMessage(msg.toString());
    }

    private void sendCommandResult(String commandId, boolean success, String output, String adminId) {
        JsonObject result = new JsonObject();
        result.addProperty("type", "result");
        result.addProperty("command_id", commandId);
        result.addProperty("success", success);
        result.addProperty("output", output);
        result.addProperty("server_id", Config.getServerId());
        result.addProperty("timestamp", System.currentTimeMillis() / 1000);
        if (adminId != null) {
            result.addProperty("admin_id", adminId);
        }

        sendMessage(result.toString());
    }

    public void sendMessage(String message) {
        WebSocket ws = webSocket;
        if (ws != null && connected.get()) {
            try {
                ws.sendText(message, true);
            } catch (Exception e) {
                LOGGER.warn("Failed to send message: {}", e.getMessage());
                connected.set(false);
            }
        } else {
            LOGGER.warn("Cannot send message, WebSocket not connected");
        }
    }

    private void scheduleReconnect() {
        if (!shouldReconnect.get()) return;

        // 取消现有重连任务
        ScheduledFuture<?> existing = reconnectFuture;
        if (existing != null) {
            existing.cancel(false);
        }

        long delay = currentReconnectDelay;
        LOGGER.info("Scheduling reconnect in {} ms", delay);
        reconnectFuture = scheduler.schedule(() -> {
            if (shouldReconnect.get()) {
                LOGGER.info("Attempting to reconnect...");
                connect();
            }
        }, delay, TimeUnit.MILLISECONDS);

        // 指数退避：5s → 10s → 20s → 40s → 60s（上限）
        currentReconnectDelay = Math.min(currentReconnectDelay * 2, MAX_RECONNECT_DELAY);
    }

    private void startHeartbeat() {
        stopHeartbeat();
        heartbeatFuture = scheduler.scheduleAtFixedRate(() -> {
            if (connected.get()) {
                JsonObject ping = new JsonObject();
                ping.addProperty("type", "ping");
                ping.addProperty("timestamp", System.currentTimeMillis());
                sendMessage(ping.toString());
            }
        }, HEARTBEAT_INTERVAL, HEARTBEAT_INTERVAL, TimeUnit.MILLISECONDS);
        LOGGER.debug("Heartbeat started");
    }

    private void stopHeartbeat() {
        ScheduledFuture<?> hb = heartbeatFuture;
        if (hb != null) {
            hb.cancel(false);
            heartbeatFuture = null;
        }
    }

    public void disconnect() {
        shouldReconnect.set(false);
        stopHeartbeat();

        ScheduledFuture<?> rc = reconnectFuture;
        if (rc != null) {
            rc.cancel(false);
            reconnectFuture = null;
        }

        WebSocket ws = webSocket;
        if (ws != null) {
            try {
                ws.sendClose(WebSocket.NORMAL_CLOSURE, "Mod shutting down");
            } catch (Exception e) {
                LOGGER.debug("Error during WebSocket close: {}", e.getMessage());
            }
        }
        connected.set(false);
        webSocket = null;
        scheduler.shutdown();
        LOGGER.info("WebSocket disconnected");
    }
}
