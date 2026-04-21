package com.mcadmin.mod.network;

import com.mcadmin.mod.MCAdminMod;
import net.minecraft.network.FriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.ResourceLocation;

public record TpsPayload(float tps, float mspt) implements CustomPacketPayload {
    public static final Type<TpsPayload> TYPE = new Type<>(
        ResourceLocation.fromNamespaceAndPath(MCAdminMod.MOD_ID, "tps"));

    public static final StreamCodec<FriendlyByteBuf, TpsPayload> STREAM_CODEC = StreamCodec.composite(
        StreamCodec.of(FriendlyByteBuf::writeFloat, FriendlyByteBuf::readFloat), TpsPayload::tps,
        StreamCodec.of(FriendlyByteBuf::writeFloat, FriendlyByteBuf::readFloat), TpsPayload::mspt,
        TpsPayload::new
    );

    @Override
    public Type<? extends CustomPacketPayload> type() {
        return TYPE;
    }
}
