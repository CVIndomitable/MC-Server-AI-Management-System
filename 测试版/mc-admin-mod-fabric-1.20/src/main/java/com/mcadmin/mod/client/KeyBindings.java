package com.mcadmin.mod.client;

import com.mojang.blaze3d.platform.InputConstants;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.minecraft.client.KeyMapping;
import org.lwjgl.glfw.GLFW;

public class KeyBindings {
    public static final KeyMapping TOGGLE_TPS_HUD = KeyBindingHelper.registerKeyBinding(new KeyMapping(
        "key.mcadmin.toggle_tps_hud",
        InputConstants.Type.KEYSYM,
        GLFW.GLFW_KEY_F8,
        "category.mcadmin"
    ));
}
