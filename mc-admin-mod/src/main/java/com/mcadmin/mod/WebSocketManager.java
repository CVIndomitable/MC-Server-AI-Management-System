package com.mcadmin.mod;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.util.Timer;
import java.util.TimerTask;

public class WebSocketManager {
    private static final Logger LOGGER = LoggerFactory.getLogger(WebSocketManager.class);
    private static final String WS_URL = "ws://localhost:8080/ws"; // 从配置读取
    private static final String AUTH_TOKEN = "test_token_123"; // 从配置读取
    private static final long RECONNECT_DELAY = 5000; // 5秒后重连

    private WebSocketClient client;
    private final CommandExecutor commandExecutor;
    private final StatusReporter statusReporter;
    private final Timer reconnectTimer;
    private boolean shouldReconnect = true;

    public WebSocketManager(CommandExecutor commandExecutor, StatusReporter statusReporter) {
        this.commandExecutor = commandExecutor;
        this.statusReporter = statusReporter;
        this.reconnectTimer = new Timer("MCAdmin-Reconnect", true);
    }

    public void connect() {
        try {
            URI uri = new URI(WS_URL);
            client = new WebSocketClient(uri) {
                @Override
                public void onOpen(ServerHandshake handshake) {
                    LOGGER.info("WebSocket connected to {}", WS_URL);
                    // 发送认证消息
                    JsonObject auth = new JsonObject();
                    auth.addProperty("type", "auth");
                    auth.addProperty("token", AUTH_TOKEN);
                    send(auth.toString());
                }

                @Override
                public void onMessage(String message) {
                    handleMessage(message);
                }

                @Override
                public void onClose(int code, String reason, boolean remote) {
                    LOGGER.warn("WebSocket closed: {} - {}", code, reason);
                    scheduleReconnect();
                }

                @Override
                public void onError(Exception ex) {
                    LOGGER.error("WebSocket error", ex);
                }
            };

            client.connect();
        } catch (Exception e) {
            LOGGER.error("Failed to connect WebSocket", e);
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
                case "auth_response":
                    boolean success = json.get("success").getAsBoolean();
                    if (success) {
                        LOGGER.info("Authentication successful");
                    } else {
                        LOGGER.error("Authentication failed");
                        disconnect();
                    }
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
        JsonObject payload = json.getAsJsonObject("payload");

        LOGGER.info("Received command: {} ({})", action, commandId);

        // 在服务器主线程执行
        commandExecutor.executeCommand(commandId, action, payload, (success, output) -> {
            sendCommandResult(commandId, success, output);
        });
    }

    private void sendCommandResult(String commandId, boolean success, String output) {
        JsonObject result = new JsonObject();
        result.addProperty("type", "result");
        result.addProperty("command_id", commandId);
        result.addProperty("success", success);
        result.addProperty("output", output);

        sendMessage(result.toString());
    }

    public void sendMessage(String message) {
        if (client != null && client.isOpen()) {
            client.send(message);
        } else {
            LOGGER.warn("Cannot send message, WebSocket not connected");
        }
    }

    private void scheduleReconnect() {
        if (!shouldReconnect) return;

        LOGGER.info("Scheduling reconnect in {} ms", RECONNECT_DELAY);
        reconnectTimer.schedule(new TimerTask() {
            @Override
            public void run() {
                if (shouldReconnect) {
                    LOGGER.info("Attempting to reconnect...");
                    connect();
                }
            }
        }, RECONNECT_DELAY);
    }

    public void disconnect() {
        shouldReconnect = false;
        if (client != null) {
            client.close();
        }
        reconnectTimer.cancel();
        LOGGER.info("WebSocket disconnected");
    }
}
