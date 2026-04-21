package com.mcadmin.mod.ai;

import com.google.gson.JsonObject;
import com.mcadmin.mod.Config;
import com.mcadmin.mod.MCAdminMod;
import com.mcadmin.mod.WebSocketManager;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * 把游戏内的玩家消息通过 WebSocket 发给后端 AI，并把回复私聊给玩家。
 */
public class AiChatBridge {
    private static final Logger LOGGER = LoggerFactory.getLogger(AiChatBridge.class);
    private static final long REQUEST_TIMEOUT_MS = 60_000;

    private record Pending(UUID playerId, long sentAtMs) {}

    private final MinecraftServer server;
    private final WebSocketManager ws;
    private final Map<String, Pending> pending = new ConcurrentHashMap<>();
    private final ScheduledExecutorService timeoutScheduler = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "MCAdmin-AiChatTimeout");
        t.setDaemon(true);
        return t;
    });

    public AiChatBridge(MinecraftServer server, WebSocketManager ws) {
        this.server = server;
        this.ws = ws;
        timeoutScheduler.scheduleWithFixedDelay(this::sweepTimeouts, 30, 30, TimeUnit.SECONDS);
    }

    public void sendChat(ServerPlayer player, String message) {
        AiSession session = AiSessionManager.get(player.getUUID());
        String requestId = "ai_" + UUID.randomUUID().toString().replace("-", "").substring(0, 16);

        JsonObject req = new JsonObject();
        req.addProperty("type", "ai_chat_request");
        req.addProperty("request_id", requestId);
        req.addProperty("server_id", Config.getServerId());
        req.addProperty("player_id", player.getUUID().toString());
        req.addProperty("player_name", player.getName().getString());
        req.addProperty("message", message);
        req.addProperty("model_tier", session.getModelTier().wire());
        req.addProperty("query_only", session.isQueryOnly());
        req.addProperty("timestamp", System.currentTimeMillis() / 1000);

        pending.put(requestId, new Pending(player.getUUID(), System.currentTimeMillis()));
        ws.sendMessage(req.toString());

        // 即时反馈，让玩家知道消息已送出
        whisper(player, Component.literal("[AI] 正在思考…").withStyle(ChatFormatting.DARK_GRAY));
    }

    public void handleResponse(JsonObject json) {
        String requestId = json.has("request_id") && !json.get("request_id").isJsonNull()
            ? json.get("request_id").getAsString() : null;
        if (requestId == null) {
            LOGGER.warn("ai_chat_response missing request_id");
            return;
        }
        Pending p = pending.remove(requestId);
        if (p == null) {
            LOGGER.warn("ai_chat_response with unknown request_id: {}", requestId);
            return;
        }

        String text = json.has("message") && !json.get("message").isJsonNull()
            ? json.get("message").getAsString() : "";
        boolean ok = !json.has("error") || json.get("error").isJsonNull();
        String errorMsg = ok ? null
            : (json.get("error").isJsonPrimitive() ? json.get("error").getAsString() : "AI 处理失败");

        server.execute(() -> {
            ServerPlayer player = server.getPlayerList().getPlayer(p.playerId());
            if (player == null) return;
            if (ok) {
                whisper(player, Component.literal("[AI] ").withStyle(ChatFormatting.AQUA)
                    .append(Component.literal(text).withStyle(ChatFormatting.WHITE)));
            } else {
                whisper(player, Component.literal("[AI] ").withStyle(ChatFormatting.AQUA)
                    .append(Component.literal(errorMsg).withStyle(ChatFormatting.RED)));
            }
        });
    }

    private void sweepTimeouts() {
        long now = System.currentTimeMillis();
        pending.entrySet().removeIf(e -> {
            if (now - e.getValue().sentAtMs() > REQUEST_TIMEOUT_MS) {
                UUID pid = e.getValue().playerId();
                server.execute(() -> {
                    ServerPlayer player = server.getPlayerList().getPlayer(pid);
                    if (player != null) {
                        whisper(player, Component.literal("[AI] 后端响应超时，请稍后重试")
                            .withStyle(ChatFormatting.RED));
                    }
                });
                return true;
            }
            return false;
        });
    }

    private static void whisper(ServerPlayer player, Component component) {
        player.sendSystemMessage(component);
    }

    public void stop() {
        timeoutScheduler.shutdownNow();
        pending.clear();
    }
}
