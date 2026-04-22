package com.mcadmin.mod.client;

import com.mcadmin.mod.MCAdminMod;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.client.event.RegisterGuiOverlaysEvent;
import net.minecraftforge.client.event.RegisterKeyMappingsEvent;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

public final class ClientEvents {

    @Mod.EventBusSubscriber(modid = MCAdminMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.MOD, value = Dist.CLIENT)
    public static class ModBus {
        @SubscribeEvent
        public static void onRegisterKeys(RegisterKeyMappingsEvent event) {
            event.register(KeyBindings.TOGGLE_TPS_HUD);
        }

        @SubscribeEvent
        public static void onRegisterGuiOverlays(RegisterGuiOverlaysEvent event) {
            event.registerAboveAll(
                new ResourceLocation(MCAdminMod.MOD_ID, "tps_hud"),
                TpsHudOverlay.INSTANCE
            );
        }
    }

    @Mod.EventBusSubscriber(modid = MCAdminMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE, value = Dist.CLIENT)
    public static class ForgeBus {
        @SubscribeEvent
        public static void onClientTick(TickEvent.ClientTickEvent event) {
            if (event.phase == TickEvent.Phase.END) {
                while (KeyBindings.TOGGLE_TPS_HUD.consumeClick()) {
                    ClientState.toggleHud();
                }
            }
        }
    }
}
