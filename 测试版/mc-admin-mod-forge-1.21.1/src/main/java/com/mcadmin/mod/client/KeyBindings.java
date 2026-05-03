package com.mcadmin.mod.client;

import com.mojang.blaze3d.platform.InputConstants;
import net.minecraft.client.KeyMapping;
import net.neoforged.neoforge.client.settings.KeyConflictContext;

public final class KeyBindings {
    public static final KeyMapping TOGGLE_TPS_HUD = new KeyMapping(
        "key.mcadmin.toggle_tps_hud",
        KeyConflictContext.IN_GAME,
        InputConstants.Type.KEYSYM,
        InputConstants.KEY_J,
        "key.categories.mcadmin"
    );

    public static final KeyMapping OPEN_AI_CHAT = new KeyMapping(
        "key.mcadmin.open_ai_chat",
        KeyConflictContext.IN_GAME,
        InputConstants.Type.KEYSYM,
        InputConstants.KEY_K,
        "key.categories.mcadmin"
    );

    private KeyBindings() {}
}
