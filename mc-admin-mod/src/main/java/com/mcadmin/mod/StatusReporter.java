package com.mcadmin.mod;

import com.google.gson.JsonObject;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Timer;
import java.util.TimerTask;

public class StatusReporter {
    private static final Logger LOGGER = LoggerFactory.getLogger(StatusReporter.class);
    private static final long REPORT_INTERVAL = 5000; // 5秒上报一次

    private final MinecraftServer server;
    private final Timer timer;
    private final List<String> recentErrors;

    public StatusReporter(MinecraftServer server) {
        this.server = server;
        this.timer = new Timer("MCAdmin-StatusReporter", true);
        this.recentErrors = new ArrayList<>();
        startReporting();
    }

    private void startReporting() {
        timer.scheduleAtFixedRate(new TimerTask() {
            @Override
            public void run() {
                reportStatus();
            }
        }, 0, REPORT_INTERVAL);
        LOGGER.info("Status reporter started");
    }

    private void reportStatus() {
        try {
            JsonObject status = collectStatus();

            JsonObject message = new JsonObject();
            message.addProperty("type", "status");
            message.addProperty("server_id", getServerId());
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

        // TPS 计算
        double tps = Math.min(20.0, server.getAverageTickTime() > 0 ?
            1000.0 / server.getAverageTickTime() : 20.0);
        data.addProperty("tps", Math.round(tps * 10.0) / 10.0);

        // 在线玩家列表
        List<String> playerNames = new ArrayList<>();
        for (ServerPlayer player : server.getPlayerList().getPlayers()) {
            playerNames.add(player.getName().getString());
        }
        data.addProperty("players", String.join(",", playerNames));
        data.addProperty("player_count", playerNames.size());
        data.addProperty("max_players", server.getMaxPlayers());

        // 内存占用
        Runtime runtime = Runtime.getRuntime();
        long usedMemory = (runtime.totalMemory() - runtime.freeMemory()) / 1024 / 1024;
        long maxMemory = runtime.maxMemory() / 1024 / 1024;
        data.addProperty("memory_used_mb", usedMemory);
        data.addProperty("memory_max_mb", maxMemory);

        // 最近错误（简化版，实际需要日志监听）
        synchronized (recentErrors) {
            data.addProperty("recent_errors", String.join("; ", recentErrors));
            recentErrors.clear();
        }

        return data;
    }

    private String getServerId() {
        // 从配置文件读取，暂时硬编码
        return "srv_001";
    }

    public void addError(String error) {
        synchronized (recentErrors) {
            recentErrors.add(error);
            if (recentErrors.size() > 10) {
                recentErrors.remove(0);
            }
        }
    }

    public void stop() {
        timer.cancel();
        LOGGER.info("Status reporter stopped");
    }
}
