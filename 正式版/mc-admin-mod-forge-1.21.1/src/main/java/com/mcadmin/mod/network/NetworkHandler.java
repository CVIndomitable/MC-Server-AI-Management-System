package com.mcadmin.mod.network;

import com.mcadmin.mod.MCAdminMod;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.network.event.RegisterPayloadHandlersEvent;
import net.neoforged.neoforge.network.registration.PayloadRegistrar;

@EventBusSubscriber(modid = MCAdminMod.MOD_ID, bus = EventBusSubscriber.Bus.MOD)
public class NetworkHandler {

    @SubscribeEvent
    public static void onRegisterPayloads(RegisterPayloadHandlersEvent event) {
        PayloadRegistrar registrar = event.registrar("1").optional();
        registrar.playToClient(
            TpsPayload.TYPE,
            TpsPayload.STREAM_CODEC,
            (payload, context) -> context.enqueueWork(() ->
                com.mcadmin.mod.client.ClientState.updateTps(payload.tps(), payload.mspt()))
        );
    }
}
