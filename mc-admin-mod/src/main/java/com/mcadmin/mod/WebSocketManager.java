package com.mcadmin.mod;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.util.Timer;
import java.util.TimerTask;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicBoolean;

public class WebSocketManager {
    private static final Logger LOGGER = LoggerFactory.getLogger(WebSocketManager.class);
    private static final long RECONNECT_DELAY = 5000;
    private static final long HEARTBEAT_INTERVAL = 30000;

    private volatile WebSocket webSocket;
    private final CommandExecutor commandExecutor;
    private final StatusReporter statusReporter;
    private Timer reconnectTimer;
    private Timer heartbeatTimer;
    private final AtomicBoolean shouldReconnect = new AtomicBoolean(true);
    private final AtomicBoolean connected = new AtomicBoolean(false);
    private final HttpClient httpClient;

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
        JsonObject payload = json.getAsJsonObject("payload");

        LOGGER.info("Received command: {} ({})", action, commandId);

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
        WebSocket ws = webSocket;
        if (ws != null && connected.get()) {
            ws.sendText(message, true);
        } else {
            LOGGER.warn("Cannot send message, WebSocket not connected");
        }
    }

    private void scheduleReconnect() {
        if (!shouldReconnect.get()) return;

        if (reconnectTimer != null) {
            reconnectTimer.cancel();
        }

        reconnectTimer = new Timer("MCAdmin-Reconnect", true);
        LOGGER.info("Scheduling reconnect in {} ms", RECONNECT_DELAY);
        reconnectTimer.schedule(new TimerTask() {
            @Override
            public void run() {
                if (shouldReconnect.get()) {
                    LOGGER.info("Attempting to reconnect...");
                    connect();
                }
            }
        }, RECONNECT_DELAY);
    }

    private void startHeartbeat() {
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

    private void stopHeartbeat() {
        if (heartbeatTimer != null) {
            heartbeatTimer.cancel();
            heartbeatTimer = null;
        }
    }

    public void disconnect() {
        shouldReconnect.set(false);
        stopHeartbeat();
        if (reconnectTimer != null) {
            reconnectTimer.cancel();
            reconnectTimer = null;
        }
        WebSocket ws = webSocket;
        if (ws != null) {
            ws.sendClose(WebSocket.NORMAL_CLOSURE, "Mod shutting down");
        }
        connected.set(false);
        webSocket = null;
        LOGGER.info("WebSocket disconnected");
    }
}
