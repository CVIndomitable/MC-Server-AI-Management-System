package com.mcadmin.mod.events;

import com.mcadmin.mod.MCAdminMod;
import com.mcadmin.mod.ai.AiChatBridge;
import com.mcadmin.mod.ai.AiSession;
import com.mcadmin.mod.ai.AiSessionManager;
import net.fabricmc.fabric.api.message.v1.ServerMessageEvents;
import net.minecraft.network.chat.ChatType;
import net.minecraft.network.chat.PlayerChatMessage;
import net.minecraft.server.level.ServerPlayer;

public class ChatInterceptor {
    private final AiChatBridge bridge;

    public ChatInterceptor(AiChatBridge bridge) {
        this.bridge = bridge;
    }

    public void onChatMessage(PlayerChatMessage message, ServerPlayer player, ChatType.Bound params) {
        if (player == null) return;

        AiSession session = AiSessionManager.getIfExists(player.getUUID());
        if (session == null || !session.isChatModeActive()) return;

        String raw = message.signedContent();
        if (raw == null) return;
        if (raw.startsWith("!")) {
            return;
        }

        // Fabric 的事件无法直接取消，需要在发送前拦截
        try {
            bridge.sendChat(player, raw);
        } catch (Exception e) {
            MCAdminMod.LOGGER.error("Failed to forward chat to AI", e);
        }
    }
}
