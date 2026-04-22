package com.mcadmin.mod.client;

/**
 * 客户端侧运行时状态：最新 TPS/MSPT 与 HUD 开关。
 * 静态字段由网络包回调和按键处理线程更新，GUI 渲染线程读取。
 */
public final class ClientState {
    private static volatile float lastTps = 20.0f;
    private static volatile float lastMspt = 0.0f;
    private static volatile long lastUpdateMs = 0L;
    private static volatile boolean hudVisible = true;

    private ClientState() {}

    public static void updateTps(float tps, float mspt) {
        lastTps = tps;
        lastMspt = mspt;
        lastUpdateMs = System.currentTimeMillis();
    }

    public static float getTps() { return lastTps; }
    public static float getMspt() { return lastMspt; }
    public static long getLastUpdateMs() { return lastUpdateMs; }

    public static boolean isHudVisible() { return hudVisible; }
    public static void toggleHud() { hudVisible = !hudVisible; }
}
