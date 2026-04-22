package com.mcadmin.mod.network;

import com.mcadmin.mod.MCAdminMod;
import com.mcadmin.mod.client.ClientState;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry;
import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.network.FriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.ResourceLocation;

public record TpsPayload(float tps, float mspt) implements CustomPacketPayload {
    public static final CustomPacketPayload.Type<TpsPayload> TYPE =
        new CustomPacketPayload.Type<>(new ResourceLocation(MCAdminMod.MOD_ID, "tps"));

    public static final StreamCodec<FriendlyByteBuf, TpsPayload> CODEC = StreamCodec.of(
        (buf, payload) -> {
            buf.writeFloat(payload.tps);
            buf.writeFloat(payload.mspt);
        },
        buf -> new TpsPayload(buf.readFloat(), buf.readFloat())
    );

    @Override
    public Type<? extends CustomPacketPayload> type() {
        return TYPE;
    }

    public static void registerClient() {
        ClientPlayNetworking.registerGlobalReceiver(TYPE, (payload, context) -> {
            context.client().execute(() -> {
                ClientState.updateTps(payload.tps(), payload.mspt());
            });
        });
    }

    public static void registerCommon() {
        PayloadTypeRegistry.playS2C().register(TYPE, CODEC);
    }
}
