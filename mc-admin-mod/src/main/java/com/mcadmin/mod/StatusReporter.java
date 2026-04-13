package com.mcadmin.mod;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.storage.ServerLevelData;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Timer;
import java.util.TimerTask;

public class StatusReporter {
    private static final Logger LOGGER = LoggerFactory.getLogger(StatusReporter.class);
    private static final int MAX_ERRORS = 50;

    private final MinecraftServer server;
    private final Timer timer;
    private final List<String> recentErrors;
    private final long reportInterval;
    private final long startTime;

    public StatusReporter(MinecraftServer server) {
        this.server = server;
        this.timer = new Timer("MCAdmin-StatusReporter", true);
        this.recentErrors = new ArrayList<>();
        this.reportInterval = Config.getReportInterval();
        this.startTime = System.currentTimeMillis();
        startReporting();
    }

    private void startReporting() {
        timer.scheduleAtFixedRate(new TimerTask() {
            @Override
            public void run() {
                reportStatus();
            }
        }, 0, reportInterval);
        LOGGER.info("Status reporter started with interval {}ms", reportInterval);
    }

    private void reportStatus() {
        try {
            JsonObject status = collectStatus();

            JsonObject message = new JsonObject();
            message.addProperty("type", "status");
            message.addProperty("server_id", Config.getServerId());
            message.addProperty("timestamp", System.currentTimeMillis() / 1000);
            message.add("data", status);

            WebSocketManager wsManager = MCAdminMod.getInstance().getWsManager();
            if (wsManager != null) {
                wsManager.sendMessage(message.toString());
            }
        } catch (Exception e) {
            LOGGER.error("Failed to report status", e);
        }
    }

    private JsonObject collectStatus() {
        JsonObject data = new JsonObject();

        // TPS 计算：使用实际tick耗时
        collectTps(data);

        // 在线玩家列表
        collectPlayers(data);

        // 内存占用
        collectMemory(data);

        // 世界信息
        collectWorldInfo(data);

        // 服务器运行时长（秒）
        data.addProperty("uptime_seconds", (System.currentTimeMillis() - startTime) / 1000);

        // 最近错误日志（数组格式）
        collectErrors(data);

        return data;
    }

    private void collectTps(JsonObject data) {
        try {
            // 通过反射获取 tickTimes/tickTimesNanos（NeoForge映射名可能不同）
            java.lang.reflect.Field field = null;
            for (java.lang.reflect.Field f : server.getClass().getSuperclass().getDeclaredFields()) {
                if (f.getType() == long[].class) {
                    f.setAccessible(true);
                    long[] arr = (long[]) f.get(server);
                    if (arr != null && arr.length >= 100) {
                        // MC的tickTimes数组固定100个元素
                        long sum = 0;
                        for (long t : arr) sum += t;
                        double avgNanos = sum / (double) arr.length;
                        double avgMs = avgNanos / 1_000_000.0;
                        double tps = Math.min(20.0, 1000.0 / Math.max(avgMs, 50.0));
                        data.addProperty("tps", Math.round(tps * 10.0) / 10.0);
                        data.addProperty("mspt", Math.round(avgMs * 10.0) / 10.0);
                        return;
                    }
                }
            }
        } catch (Exception e) {
            // 反射失败，使用 fallback
        }

        // Fallback: tickRateManager（返回目标tick率）
        double msPerTick = server.tickRateManager().millisecondsPerTick();
        double tps = Math.min(20.0, msPerTick > 0 ? 1000.0 / msPerTick : 20.0);
        data.addProperty("tps", Math.round(tps * 10.0) / 10.0);
    }

    private void collectPlayers(JsonObject data) {
        JsonArray playerArray = new JsonArray();
        for (ServerPlayer player : server.getPlayerList().getPlayers()) {
            playerArray.add(player.getName().getString());
        }
        data.add("players", playerArray);
        data.addProperty("player_count", playerArray.size());
        data.addProperty("max_players", server.getMaxPlayers());
    }

    private void collectMemory(JsonObject data) {
        Runtime runtime = Runtime.getRuntime();
        long usedMemory = (runtime.totalMemory() - runtime.freeMemory()) / 1024 / 1024;
        long maxMemory = runtime.maxMemory() / 1024 / 1024;
        data.addProperty("memory_used_mb", usedMemory);
        data.addProperty("memory_max_mb", maxMemory);
    }

    private void collectWorldInfo(JsonObject data) {
        try {
            ServerLevel overworld = server.overworld();
            if (overworld == null) return;

            JsonObject world = new JsonObject();

            // 游戏时间（tick）和天数
            long dayTime = overworld.getDayTime();
            world.addProperty("day_time", dayTime);
            world.addProperty("day_count", dayTime / 24000);

            // 天气状态
            if (overworld.isThundering()) {
                world.addProperty("weather", "thunder");
            } else if (overworld.isRaining()) {
                world.addProperty("weather", "rain");
            } else {
                world.addProperty("weather", "clear");
            }

            // 难度
            world.addProperty("difficulty", server.getWorldData().getDifficulty().getKey());

            data.add("world", world);
        } catch (Exception e) {
            LOGGER.debug("Failed to collect world info: {}", e.getMessage());
        }
    }

    private void collectErrors(JsonObject data) {
        synchronized (recentErrors) {
            JsonArray errArray = new JsonArray();
            for (String err : recentErrors) {
                errArray.add(err);
            }
            data.add("recent_errors", errArray);
            recentErrors.clear();
        }
    }

    public void addError(String error) {
        synchronized (recentErrors) {
            recentErrors.add(error);
            if (recentErrors.size() > MAX_ERRORS) {
                recentErrors.remove(0);
            }
        }
    }

    public void stop() {
        timer.cancel();
        LOGGER.info("Status reporter stopped");
    }
}
