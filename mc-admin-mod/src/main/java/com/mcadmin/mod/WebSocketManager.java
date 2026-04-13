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
import java.util.Timer;
import java.util.TimerTask;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicBoolean;

public class WebSocketManager {
    private static final Logger LOGGER = LoggerFactory.getLogger(WebSocketManager.class);
    private static final long INITIAL_RECONNECT_DELAY = 5000;
    private static final long MAX_RECONNECT_DELAY = 60000;
    private static final long HEARTBEAT_INTERVAL = 30000;

    private volatile WebSocket webSocket;
    private final CommandExecutor commandExecutor;
    private final StatusReporter statusReporter;
    private Timer reconnectTimer;
    private Timer heartbeatTimer;
    private final AtomicBoolean shouldReconnect = new AtomicBoolean(true);
    private final AtomicBoolean connected = new AtomicBoolean(false);
    private final HttpClient httpClient;
    private long currentReconnectDelay = INITIAL_RECONNECT_DELAY;

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

            String separator = wsUrl.contains("?") ? "&" : "?";
            String fullUrl = wsUrl + separator + "server_id=" + serverId + "&token=" + authToken;

            LOGGER.info("Connecting to WebSocket: {}", wsUrl);

            httpClient.newWebSocketBuilder()
                .buildAsync(URI.create(fullUrl), new WebSocket.Listener() {
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
            String type = json.get("type").getAsString();

            switch (type) {
                case "command":
                    handleCommand(json);
                    break;
                case "update_whitelist":
                    handleWhitelistUpdate(json);
                    break;
                case "auth_response":
                    LOGGER.debug("Received auth_response (auth handled via query params)");
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
        String commandId = json.get("id").getAsString();
        String action = json.get("action").getAsString();
        JsonObject payload = json.has("payload") ? json.getAsJsonObject("payload") : new JsonObject();

        // 提取扩展字段
        String adminId = payload.has("admin_id") ? payload.get("admin_id").getAsString() : null;
        boolean confirmed = payload.has("confirmed") && payload.get("confirmed").getAsBoolean();

        LOGGER.info("Received command: {} ({}) from admin: {}", action, commandId,
            adminId != null ? adminId : "unknown");

        // 二次确认检查：危险操作 + 开启确认 + 未确认 → 拒绝并要求确认
        if (Config.requireConfirmation() && !confirmed
                && commandExecutor.isDangerousAction(action, payload)) {
            String detail = commandExecutor.describeCommand(action, payload);
            LOGGER.warn("Dangerous command requires confirmation: {} ({})", detail, commandId);
            sendConfirmRequired(commandId, action, detail, adminId);
            return;
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
        if (!json.has("commands")) {
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

    private synchronized void scheduleReconnect() {
        if (!shouldReconnect.get()) return;

        if (reconnectTimer != null) {
            reconnectTimer.cancel();
        }

        reconnectTimer = new Timer("MCAdmin-Reconnect", true);
        LOGGER.info("Scheduling reconnect in {} ms", currentReconnectDelay);
        long delay = currentReconnectDelay;
        reconnectTimer.schedule(new TimerTask() {
            @Override
            public void run() {
                if (shouldReconnect.get()) {
                    LOGGER.info("Attempting to reconnect...");
                    connect();
                }
            }
        }, delay);

        // 指数退避：5s → 10s → 20s → 40s → 60s（上限）
        currentReconnectDelay = Math.min(currentReconnectDelay * 2, MAX_RECONNECT_DELAY);
    }

    private synchronized void startHeartbeat() {
        stopHeartbeat();
        heartbeatTimer = new Timer("MCAdmin-Heartbeat", true);
        heartbeatTimer.scheduleAtFixedRate(new TimerTask() {
            @Override
            public void run() {
                if (connected.get()) {
                    JsonObject ping = new JsonObject();
                    ping.addProperty("type", "ping");
                    ping.addProperty("timestamp", System.currentTimeMillis());
                    sendMessage(ping.toString());
                }
            }
        }, HEARTBEAT_INTERVAL, HEARTBEAT_INTERVAL);
        LOGGER.debug("Heartbeat started");
    }

    private synchronized void stopHeartbeat() {
        if (heartbeatTimer != null) {
            heartbeatTimer.cancel();
            heartbeatTimer = null;
        }
    }

    public void disconnect() {
        shouldReconnect.set(false);
        stopHeartbeat();
        synchronized (this) {
            if (reconnectTimer != null) {
                reconnectTimer.cancel();
                reconnectTimer = null;
            }
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
        LOGGER.info("WebSocket disconnected");
    }
}
