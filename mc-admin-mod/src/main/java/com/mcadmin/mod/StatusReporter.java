package com.mcadmin.mod;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.storage.ServerLevelData;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.lang.management.ManagementFactory;
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
        // 初始延迟 = reportInterval，避免 WebSocketManager 尚未初始化时的无效调用
        timer.scheduleAtFixedRate(new TimerTask() {
            @Override
            public void run() {
                reportStatus();
            }
        }, reportInterval, reportInterval);
        LOGGER.info("Status reporter started with interval {}ms", reportInterval);
    }

    private void reportStatus() {
        try {
            // 在服务器主线程收集数据，避免跨线程读取 MC 对象导致并发问题
            server.execute(() -> {
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
                    LOGGER.error("Failed to collect/send status", e);
                }
            });
        } catch (Exception e) {
            LOGGER.error("Failed to schedule status report", e);
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

        // CPU使用率
        collectCpu(data);

        // 世界信息
        collectWorldInfo(data);

        // Spark 详细性能数据（TPS多窗口、MSPT百分位、CPU、GC）
        collectSparkData(data);

        // 服务器运行时长（秒）
        data.addProperty("uptime_seconds", (System.currentTimeMillis() - startTime) / 1000);

        // 最近错误日志（数组格式）
        collectErrors(data);

        return data;
    }

    // 缓存反射字段，避免每次上报都遍历
    private java.lang.reflect.Field tickTimesField;
    private boolean tickTimesFieldResolved = false;

    private void collectTps(JsonObject data) {
        try {
            if (!tickTimesFieldResolved) {
                tickTimesFieldResolved = true;
                tickTimesField = resolveTickTimesField();
            }

            if (tickTimesField != null) {
                long[] arr = (long[]) tickTimesField.get(server);
                if (arr != null) {
                    long sum = 0;
                    for (long t : arr) sum += t;
                    double avgNanos = sum / (double) arr.length;
                    // 合理性校验：tick 耗时应在 0~10 秒（纳秒级）范围内
                    if (avgNanos > 0 && avgNanos < 10_000_000_000L) {
                        double avgMs = avgNanos / 1_000_000.0;
                        double tps = Math.min(20.0, 1000.0 / Math.max(avgMs, 50.0));
                        data.addProperty("tps", Math.round(tps * 10.0) / 10.0);
                        data.addProperty("mspt", Math.round(avgMs * 10.0) / 10.0);
                        return;
                    }
                }
            }
        } catch (Exception e) {
            LOGGER.debug("Reflection TPS collection failed: {}", e.getMessage());
        }

        // Fallback: tickRateManager（返回目标tick率）
        double msPerTick = server.tickRateManager().millisecondsPerTick();
        double tps = Math.min(20.0, msPerTick > 0 ? 1000.0 / msPerTick : 20.0);
        data.addProperty("tps", Math.round(tps * 10.0) / 10.0);
    }

    /**
     * 解析 tickTimes 字段：优先按已知名称匹配，回退到类型+长度匹配
     */
    private java.lang.reflect.Field resolveTickTimesField() {
        String[] knownNames = {"tickTimes", "tickTimesNanos", "f_129744_"};
        // 搜索当前类和父类
        for (Class<?> clazz = server.getClass(); clazz != null; clazz = clazz.getSuperclass()) {
            for (java.lang.reflect.Field f : clazz.getDeclaredFields()) {
                if (f.getType() == long[].class) {
                    // 优先按名称匹配
                    for (String name : knownNames) {
                        if (f.getName().equals(name)) {
                            try {
                                f.setAccessible(true);
                                long[] arr = (long[]) f.get(server);
                                if (arr != null && arr.length == 100) {
                                    LOGGER.info("Resolved tickTimes field by name: {}", f.getName());
                                    return f;
                                }
                            } catch (Exception ignored) {}
                        }
                    }
                }
            }
        }
        // 回退：按 long[100] 类型匹配
        for (Class<?> clazz = server.getClass(); clazz != null; clazz = clazz.getSuperclass()) {
            for (java.lang.reflect.Field f : clazz.getDeclaredFields()) {
                if (f.getType() == long[].class) {
                    try {
                        f.setAccessible(true);
                        long[] arr = (long[]) f.get(server);
                        if (arr != null && arr.length == 100) {
                            LOGGER.info("Resolved tickTimes field by type: {}.{}", clazz.getSimpleName(), f.getName());
                            return f;
                        }
                    } catch (Exception ignored) {}
                }
            }
        }
        LOGGER.warn("Could not resolve tickTimes field, using fallback TPS");
        return null;
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

    private void collectCpu(JsonObject data) {
        try {
            var osBean = ManagementFactory.getOperatingSystemMXBean();
            if (osBean instanceof com.sun.management.OperatingSystemMXBean sunBean) {
                double processCpu = sunBean.getProcessCpuLoad();
                double systemCpu = sunBean.getCpuLoad();
                // 返回值为 0.0~1.0，转为百分比，保留一位小数；负值表示不可用
                if (processCpu >= 0) {
                    data.addProperty("cpu_process", Math.round(processCpu * 1000.0) / 10.0);
                }
                if (systemCpu >= 0) {
                    data.addProperty("cpu_system", Math.round(systemCpu * 1000.0) / 10.0);
                }
            }
            data.addProperty("cpu_cores", osBean.getAvailableProcessors());
        } catch (Exception e) {
            LOGGER.debug("Failed to collect CPU info: {}", e.getMessage());
        }
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

    private void collectSparkData(JsonObject data) {
        try {
            JsonObject sparkData = SparkIntegration.collectSparkData();
            if (sparkData != null) {
                data.add("spark", sparkData);
            }
        } catch (Exception e) {
            LOGGER.debug("Spark data collection skipped: {}", e.getMessage());
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
