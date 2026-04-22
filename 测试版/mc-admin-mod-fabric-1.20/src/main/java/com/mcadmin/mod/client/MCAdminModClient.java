package com.mcadmin.mod.client;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;

public class MCAdminModClient implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        // 注册客户端网络包接收
        com.mcadmin.mod.network.TpsPayload.registerClient();

        KeyBindingHelper.registerKeyBinding(KeyBindings.TOGGLE_TPS_HUD);

        HudRenderCallback.EVENT.register((drawContext, tickDelta) -> {
            TpsHudOverlay.INSTANCE.render(drawContext, tickDelta);
        });

        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            while (KeyBindings.TOGGLE_TPS_HUD.consumeClick()) {
                ClientState.toggleHud();
            }
        });
    }
}
