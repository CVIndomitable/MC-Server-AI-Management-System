package com.mcadmin.mod.events;

import com.mcadmin.mod.MCAdminMod;
import com.mcadmin.mod.ai.AiChatBridge;
import com.mcadmin.mod.ai.AiSession;
import com.mcadmin.mod.ai.AiSessionManager;
import net.minecraft.server.level.ServerPlayer;
import net.minecraftforge.event.ServerChatEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;

public class ChatInterceptor {
    private final AiChatBridge bridge;

    public ChatInterceptor(AiChatBridge bridge) {
        this.bridge = bridge;
    }

    @SubscribeEvent
    public void onServerChat(ServerChatEvent event) {
        ServerPlayer player = event.getPlayer();
        if (player == null) return;

        AiSession session = AiSessionManager.getIfExists(player.getUUID());
        if (session == null || !session.isChatModeActive()) return;

        // 以 "!" 开头允许绕过 AI 转发，照常在聊天框发言
        String raw = event.getRawText();
        if (raw == null) return;
        if (raw.startsWith("!")) {
            // 去掉前缀，按普通聊天处理
            return;
        }

        event.setCanceled(true);
        try {
            bridge.sendChat(player, raw);
        } catch (Exception e) {
            MCAdminMod.LOGGER.error("Failed to forward chat to AI", e);
        }
    }
}
