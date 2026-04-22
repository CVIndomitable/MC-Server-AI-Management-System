package com.mcadmin.mod.client;

public class ClientState {
    private static float tps = 20.0f;
    private static float mspt = 0.0f;
    private static long lastUpdateMs = 0L;
    private static boolean hudVisible = false;

    public static void updateTps(float newTps, float newMspt) {
        tps = newTps;
        mspt = newMspt;
        lastUpdateMs = System.currentTimeMillis();
    }

    public static float getTps() {
        return tps;
    }

    public static float getMspt() {
        return mspt;
    }

    public static long getLastUpdateMs() {
        return lastUpdateMs;
    }

    public static boolean isHudVisible() {
        return hudVisible;
    }

    public static void toggleHud() {
        hudVisible = !hudVisible;
    }
}
