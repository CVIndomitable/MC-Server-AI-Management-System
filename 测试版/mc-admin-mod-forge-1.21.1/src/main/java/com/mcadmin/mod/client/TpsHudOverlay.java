package com.mcadmin.mod.client;

import net.minecraft.ChatFormatting;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.LayeredDraw;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MutableComponent;

public final class TpsHudOverlay implements LayeredDraw.Layer {
    public static final TpsHudOverlay INSTANCE = new TpsHudOverlay();

    private TpsHudOverlay() {}

    @Override
    public void render(GuiGraphics gui, DeltaTracker deltaTracker) {
        if (!ClientState.isHudVisible()) return;
        Minecraft mc = Minecraft.getInstance();
        if (mc.options.hideGui || mc.player == null) return;

        float tps = ClientState.getTps();
        float mspt = ClientState.getMspt();
        long age = System.currentTimeMillis() - ClientState.getLastUpdateMs();
        boolean stale = ClientState.getLastUpdateMs() == 0L || age > 15_000L;

        ChatFormatting tpsColor = stale ? ChatFormatting.GRAY
            : tps >= 19.5f ? ChatFormatting.GREEN
            : tps >= 15.0f ? ChatFormatting.YELLOW
            : ChatFormatting.RED;

        MutableComponent line = Component.literal("TPS ")
            .append(Component.literal(String.format("%.1f", tps)).withStyle(tpsColor))
            .append(Component.literal("  MSPT "))
            .append(Component.literal(String.format("%.1f", mspt)).withStyle(tpsColor));
        if (stale) {
            line = line.append(Component.literal(" (?)").withStyle(ChatFormatting.DARK_GRAY));
        }

        int screenWidth = gui.guiWidth();
        int textWidth = mc.font.width(line);
        int x = screenWidth - textWidth - 4;
        int y = 4;
        gui.drawString(mc.font, line, x, y, 0xFFFFFF, true);
    }
}
