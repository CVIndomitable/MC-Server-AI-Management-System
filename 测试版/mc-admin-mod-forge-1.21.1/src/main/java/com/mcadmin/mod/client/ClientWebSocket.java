package com.mcadmin.mod.client;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mcadmin.mod.Config;
import com.mcadmin.mod.MCAdminMod;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 客户端侧 WebSocket 连接管理，仅处理 AI 聊天消息。
 */
public class ClientWebSocket {
    private static final Logger LOGGER = LoggerFactory.getLogger(ClientWebSocket.class);
    private static final long INITIAL_RECONNECT_DELAY = 5000;
    private static final long MAX_RECONNECT_DELAY = 60000;
    private static final long HEARTBEAT_INTERVAL = 30000;
    private static final long RECONNECT_RESET_THRESHOLD = 300000;

    private volatile WebSocket webSocket;
    private final HttpClient httpClient;
    private final ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "MCAdmin-ClientWS");
            t.setDaemon(true);
            return t;
        });

    private final AtomicBoolean shouldReconnect = new AtomicBoolean(true);
    private final AtomicBoolean connected = new AtomicBoolean(false);
    private volatile long currentReconnectDelay = INITIAL_RECONNECT_DELAY;
    private volatile long lastSuccessfulConnectionTime = 0;

    private volatile ScheduledFuture<?> reconnectFuture;
    private volatile ScheduledFuture<?> heartbeatFuture;

    private volatile String playerUuid;
    private volatile String playerName;
    private volatile String serverId;

    public interface MessageHandler {
        void onAiChatResponse(JsonObject json);
        void onConnectionStateChanged(boolean connected);
    }

    private volatile MessageHandler messageHandler;

    public void setMessageHandler(MessageHandler handler) {
        this.messageHandler = handler;
    }

    public void setPlayerIdentity(String uuid, String name, String serverId) {
        this.playerUuid = uuid;
        this.playerName = name;
        this.serverId = serverId;
    }

    public boolean isConnected() {
        return connected.get();
    }

    public ClientWebSocket() {
        this.httpClient = HttpClient.newHttpClient();
    }

    public void connect() {
        if (playerUuid == null || playerUuid.isEmpty()) {
            LOGGER.warn("ClientWebSocket: player identity not set, skipping connect");
            return;
        }

        String token = Config.getAuthToken();
        if (token.equals("change-me-in-config-file")) {
            LOGGER.warn("ClientWebSocket: ws.token not configured, skipping connect");
            return;
        }

        try {
            String wsUrl = Config.getClientWsUrl();
            LOGGER.info("ClientWebSocket connecting to: {}", wsUrl);

            httpClient.newWebSocketBuilder()
                .header("Authorization", "Bearer " + token)
                .buildAsync(URI.create(wsUrl), new WebSocket.Listener() {
                    private final StringBuilder messageBuffer = new StringBuilder();

                    @Override
                    public void onOpen(WebSocket ws) {
                        LOGGER.info("ClientWebSocket connected to {}", wsUrl);
                        webSocket = ws;
                        connected.set(true);

                        // 重置重连延迟：如果距离上次成功连接超过阈值，说明连接稳定
                        long now = System.currentTimeMillis();
                        if (lastSuccessfulConnectionTime > 0 &&
                            (now - lastSuccessfulConnectionTime) > RECONNECT_RESET_THRESHOLD) {
                            currentReconnectDelay = INITIAL_RECONNECT_DELAY;
                        }
                        lastSuccessfulConnectionTime = now;

                        sendClientHello();
                        startHeartbeat();
                        notifyConnectionState(true);
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
                        LOGGER.warn("ClientWebSocket closed: {} - {}", statusCode, reason);
                        connected.set(false);
                        webSocket = null;
                        stopHeartbeat();
                        notifyConnectionState(false);
                        scheduleReconnect();
                        return null;
                    }

                    @Override
                    public void onError(WebSocket ws, Throwable error) {
                        LOGGER.error("ClientWebSocket error: {}", error.getMessage());
                        connected.set(false);
                        webSocket = null;
                        stopHeartbeat();
                        notifyConnectionState(false);
                        scheduleReconnect();
                    }
                })
                .exceptionally(ex -> {
                    LOGGER.error("ClientWebSocket connection failed: {}", ex.getMessage());
                    scheduleReconnect();
                    return null;
                });
        } catch (Exception e) {
            LOGGER.error("ClientWebSocket init failed", e);
            scheduleReconnect();
        }
    }

    public void sendAiChatRequest(String requestId, String message, String modelTier) {
        if (!connected.get() || webSocket == null) return;

        JsonObject req = new JsonObject();
        req.addProperty("type", "ai_chat_request");
        req.addProperty("request_id", requestId);
        req.addProperty("message", message);
        req.addProperty("model_tier", modelTier);
        req.addProperty("player_uuid", playerUuid);
        req.addProperty("player_name", playerName);

        try {
            webSocket.sendText(req.toString(), true);
        } catch (Exception e) {
            LOGGER.warn("ClientWebSocket send failed: {}", e.getMessage());
            connected.set(false);
        }
    }

    private void sendClientHello() {
        if (!connected.get() || webSocket == null) return;

        JsonObject hello = new JsonObject();
        hello.addProperty("type", "client_hello");
        hello.addProperty("player_uuid", playerUuid);
        hello.addProperty("player_name", playerName);
        hello.addProperty("server_id", serverId);

        try {
            webSocket.sendText(hello.toString(), true);
        } catch (Exception e) {
            LOGGER.warn("ClientWebSocket client_hello send failed: {}", e.getMessage());
        }
    }

    private void handleMessage(String message) {
        try {
            JsonObject json = JsonParser.parseString(message).getAsJsonObject();
            if (!json.has("type") || json.get("type").isJsonNull()) return;
            String type = json.get("type").getAsString();

            switch (type) {
                case "ai_chat_response":
                    if (messageHandler != null) {
                        messageHandler.onAiChatResponse(json);
                    }
                    break;
                case "pong":
                    break;
            }
        } catch (Exception e) {
            LOGGER.error("ClientWebSocket message handling error: {}", e.getMessage());
        }
    }

    private void scheduleReconnect() {
        if (!shouldReconnect.get()) return;

        ScheduledFuture<?> existing = reconnectFuture;
        if (existing != null) {
            existing.cancel(false);
        }

        long delay = currentReconnectDelay;
        LOGGER.info("ClientWebSocket scheduling reconnect in {} ms", delay);
        reconnectFuture = scheduler.schedule(() -> {
            if (shouldReconnect.get()) {
                connect();
            }
        }, delay, TimeUnit.MILLISECONDS);

        currentReconnectDelay = Math.min(currentReconnectDelay * 2, MAX_RECONNECT_DELAY);
    }

    private void startHeartbeat() {
        stopHeartbeat();
        heartbeatFuture = scheduler.scheduleAtFixedRate(() -> {
            if (connected.get() && webSocket != null) {
                JsonObject ping = new JsonObject();
                ping.addProperty("type", "ping");
                try {
                    webSocket.sendText(ping.toString(), true);
                } catch (Exception ignored) {}
            }
        }, HEARTBEAT_INTERVAL, HEARTBEAT_INTERVAL, TimeUnit.MILLISECONDS);
    }

    private void stopHeartbeat() {
        ScheduledFuture<?> hb = heartbeatFuture;
        if (hb != null) {
            hb.cancel(false);
            heartbeatFuture = null;
        }
    }

    private void notifyConnectionState(boolean state) {
        if (messageHandler != null) {
            messageHandler.onConnectionStateChanged(state);
        }
    }

    public void shutdown() {
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
                ws.sendClose(WebSocket.NORMAL_CLOSURE, "Client shutting down");
            } catch (Exception ignored) {}
        }
        connected.set(false);
        webSocket = null;
        scheduler.shutdown();
        try {
            if (!scheduler.awaitTermination(3, TimeUnit.SECONDS)) {
                scheduler.shutdownNow();
            }
        } catch (InterruptedException e) {
            scheduler.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
