package com.mcadmin.mod.client;

import com.mcadmin.mod.MCAdminMod;
import net.minecraft.resources.ResourceLocation;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.client.event.RegisterGuiLayersEvent;
import net.neoforged.neoforge.client.event.RegisterKeyMappingsEvent;
import net.neoforged.neoforge.client.event.ClientTickEvent;

public final class ClientEvents {

    @EventBusSubscriber(modid = MCAdminMod.MOD_ID, bus = EventBusSubscriber.Bus.MOD, value = Dist.CLIENT)
    public static class ModBus {
        @SubscribeEvent
        public static void onRegisterKeys(RegisterKeyMappingsEvent event) {
            event.register(KeyBindings.TOGGLE_TPS_HUD);
        }

        @SubscribeEvent
        public static void onRegisterGuiLayers(RegisterGuiLayersEvent event) {
            event.registerAboveAll(
                ResourceLocation.fromNamespaceAndPath(MCAdminMod.MOD_ID, "tps_hud"),
                TpsHudOverlay.INSTANCE
            );
        }
    }

    @EventBusSubscriber(modid = MCAdminMod.MOD_ID, bus = EventBusSubscriber.Bus.GAME, value = Dist.CLIENT)
    public static class GameBus {
        @SubscribeEvent
        public static void onClientTick(ClientTickEvent.Post event) {
            while (KeyBindings.TOGGLE_TPS_HUD.consumeClick()) {
                ClientState.toggleHud();
            }
        }
    }
}
