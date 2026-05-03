package com.mcadmin.mod.client;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;
import java.util.concurrent.*;

/**
 * 客户端 AI 聊天协调器，管理消息、速率限制、WebSocket连接。
 */
public class ClientAiChat {
    private static final Logger LOGGER = LoggerFactory.getLogger(ClientAiChat.class);
    private static final int MAX_HISTORY = 200;
    private static final int RATE_LIMIT_MESSAGES = 10;
    private static final long RATE_LIMIT_WINDOW_MS = 60_000;
    private static final long REQUEST_TIMEOUT_MS = 60_000;

    private static ClientAiChat instance;

    private final ClientWebSocket webSocket;
    private final List<ChatMessage> messageHistory = new ArrayList<>();
    private final List<ChatListener> listeners = new CopyOnWriteArrayList<>();
    private final Map<String, PendingRequest> pending = new ConcurrentHashMap<>();
    private final Map<UUID, RateLimitEntry> rateLimits = new ConcurrentHashMap<>();
    private final ScheduledExecutorService timeoutScheduler = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "MCAdmin-ChatTimeout");
        t.setDaemon(true);
        return t;
    });

    public enum Sender { PLAYER, AI, SYSTEM }

    public record ChatMessage(Sender sender, String text, long timestamp) {}

    private record PendingRequest(long sentAtMs) {}
    private record RateLimitEntry(int count, long windowStartMs) {}

    public interface ChatListener {
        void onMessageAdded(ChatMessage message);
        void onConnectionStateChanged(boolean connected);
    }

    private ClientAiChat() {
        this.webSocket = new ClientWebSocket();
        this.webSocket.setMessageHandler(new ClientWebSocket.MessageHandler() {
            @Override
            public void onAiChatResponse(JsonObject json) {
                handleResponse(json);
            }

            @Override
            public void onConnectionStateChanged(boolean connected) {
                for (ChatListener l : listeners) {
                    l.onConnectionStateChanged(connected);
                }
                if (!connected) {
                    postToRender(() -> {
                        addMessage(Sender.SYSTEM, "连接已断开，正在重连…");
                    });
                }
            }
        });
        timeoutScheduler.scheduleWithFixedDelay(this::sweepTimeouts, 30, 30, TimeUnit.SECONDS);
        timeoutScheduler.scheduleWithFixedDelay(this::cleanupRateLimits, 60, 60, TimeUnit.SECONDS);
    }

    public static ClientAiChat getInstance() {
        if (instance == null) {
            instance = new ClientAiChat();
        }
        return instance;
    }

    public void addListener(ChatListener listener) {
        listeners.add(listener);
    }

    public void removeListener(ChatListener listener) {
        listeners.remove(listener);
    }

    public List<ChatMessage> getMessageHistory() {
        return Collections.unmodifiableList(messageHistory);
    }

    public boolean isConnected() {
        return webSocket.isConnected();
    }

    public void initialize() {
        Minecraft mc = Minecraft.getInstance();
        if (mc.player == null) return;

        String uuid = mc.player.getGameProfile().getId().toString();
        String name = mc.player.getGameProfile().getName();
        String serverId = com.mcadmin.mod.Config.getServerId();
        webSocket.setPlayerIdentity(uuid, name, serverId);
        webSocket.connect();

        addMessage(Sender.SYSTEM, "AI对话已就绪，输入问题开始交流");
    }

    public void sendMessage(String text) {
        Minecraft mc = Minecraft.getInstance();
        if (mc.player == null) return;

        if (!checkRateLimit()) return;

        addMessage(Sender.PLAYER, text);

        String requestId = "cai_" + UUID.randomUUID().toString().replace("-", "").substring(0, 16);
        pending.put(requestId, new PendingRequest(System.currentTimeMillis()));

        addMessage(Sender.SYSTEM, "AI正在思考…");

        webSocket.sendAiChatRequest(requestId, text, "flash");
    }

    private boolean checkRateLimit() {
        Minecraft mc = Minecraft.getInstance();
        if (mc.player == null) return false;

        UUID playerId = mc.player.getUUID();
        long now = System.currentTimeMillis();

        RateLimitEntry entry = rateLimits.compute(playerId, (k, v) -> {
            if (v == null || now - v.windowStartMs >= RATE_LIMIT_WINDOW_MS) {
                return new RateLimitEntry(1, now);
            } else {
                return new RateLimitEntry(v.count + 1, v.windowStartMs);
            }
        });

        if (entry.count > RATE_LIMIT_MESSAGES) {
            long remainingMs = RATE_LIMIT_WINDOW_MS - (now - entry.windowStartMs);
            postToRender(() -> {
                addMessage(Sender.SYSTEM, "消息发送过快，请等待 " + (remainingMs / 1000) + " 秒");
            });
            return false;
        }
        return true;
    }

    private void handleResponse(JsonObject json) {
        String requestId = json.has("request_id") && !json.get("request_id").isJsonNull()
            ? json.get("request_id").getAsString() : null;
        if (requestId == null) return;

        pending.remove(requestId);

        String text = json.has("message") && !json.get("message").isJsonNull()
            ? json.get("message").getAsString() : "";
        boolean hasError = json.has("error") && !json.get("error").isJsonNull();
        String errorMsg = hasError ? json.get("error").getAsString() : null;

        // 移除最后一条"AI正在思考…"消息并添加新消息
        postToRender(() -> {
            removeThinkingMessage();
            if (hasError) {
                addMessage(Sender.SYSTEM, errorMsg != null ? errorMsg : "AI处理失败");
            } else {
                addMessage(Sender.AI, text);
            }
        });
    }

    private void removeThinkingMessage() {
        synchronized (messageHistory) {
            if (!messageHistory.isEmpty()) {
                ChatMessage last = messageHistory.get(messageHistory.size() - 1);
                if (last.sender == Sender.SYSTEM && last.text.equals("AI正在思考…")) {
                    messageHistory.remove(messageHistory.size() - 1);
                }
            }
        }
    }

    private void addMessage(Sender sender, String text) {
        ChatMessage msg = new ChatMessage(sender, text, System.currentTimeMillis());
        synchronized (messageHistory) {
            messageHistory.add(msg);
            if (messageHistory.size() > MAX_HISTORY) {
                messageHistory.remove(0);
            }
        }
        for (ChatListener l : listeners) {
            l.onMessageAdded(msg);
        }
    }

    private void sweepTimeouts() {
        long now = System.currentTimeMillis();
        pending.entrySet().removeIf(e -> {
            if (now - e.getValue().sentAtMs > REQUEST_TIMEOUT_MS) {
                postToRender(() -> {
                    addMessage(Sender.SYSTEM, "AI响应超时，请稍后重试");
                });
                return true;
            }
            return false;
        });
    }

    private void cleanupRateLimits() {
        long now = System.currentTimeMillis();
        rateLimits.entrySet().removeIf(e -> now - e.getValue().windowStartMs >= RATE_LIMIT_WINDOW_MS);
    }

    private void postToRender(Runnable task) {
        Minecraft mc = Minecraft.getInstance();
        mc.execute(task);
    }

    public void shutdown() {
        webSocket.shutdown();
        pending.clear();
        timeoutScheduler.shutdown();
        try {
            if (!timeoutScheduler.awaitTermination(3, TimeUnit.SECONDS)) {
                timeoutScheduler.shutdownNow();
            }
        } catch (InterruptedException e) {
            timeoutScheduler.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
