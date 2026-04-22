package com.mcadmin.mod.network;

import com.mcadmin.mod.MCAdminMod;
import net.minecraft.network.FriendlyByteBuf;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.network.NetworkEvent;

import java.util.function.Supplier;

public class TpsPayload {
    private final float tps;
    private final float mspt;

    public TpsPayload(float tps, float mspt) {
        this.tps = tps;
        this.mspt = mspt;
    }

    public static void encode(TpsPayload msg, FriendlyByteBuf buf) {
        buf.writeFloat(msg.tps);
        buf.writeFloat(msg.mspt);
    }

    public static TpsPayload decode(FriendlyByteBuf buf) {
        return new TpsPayload(buf.readFloat(), buf.readFloat());
    }

    public static void handle(TpsPayload msg, Supplier<NetworkEvent.Context> ctx) {
        ctx.get().enqueueWork(() -> {
            com.mcadmin.mod.client.ClientState.updateTps(msg.tps, msg.mspt);
        });
        ctx.get().setPacketHandled(true);
    }

    public float tps() {
        return tps;
    }

    public float mspt() {
        return mspt;
    }
}
