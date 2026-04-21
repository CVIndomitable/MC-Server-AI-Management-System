package com.mcadmin.mod;

import com.google.gson.JsonObject;
import net.minecraft.server.MinecraftServer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.function.BiConsumer;

/**
 * 读取服务器最新日志文件（logs/latest.log），供 AI 排查问题使用。
 * 文件 I/O 不在主线程执行，避免阻塞 tick loop。
 */
public class LogReader {
    private static final Logger LOGGER = LoggerFactory.getLogger(LogReader.class);
    private static final int DEFAULT_LINES = 200;
    private static final int MAX_LINES = 500;
    private static final int MAX_OUTPUT_CHARS = 8000;

    private final MinecraftServer server;

    public LogReader(MinecraftServer server) {
        this.server = server;
    }

    public void readLatest(JsonObject payload, BiConsumer<Boolean, String> callback) {
        int requested = DEFAULT_LINES;
        if (payload != null && payload.has("lines") && !payload.get("lines").isJsonNull()) {
            try {
                requested = payload.get("lines").getAsInt();
            } catch (Exception ignored) {}
        }
        final int lineLimit = Math.max(1, Math.min(MAX_LINES, requested));

        String kwRaw = null;
        if (payload != null && payload.has("keyword") && !payload.get("keyword").isJsonNull()) {
            String k = payload.get("keyword").getAsString().trim();
            if (!k.isEmpty()) kwRaw = k.toLowerCase();
        }
        final String keyword = kwRaw;

        try {
            File serverDir = server.getServerDirectory().toFile().getCanonicalFile();
            File logsDir = new File(serverDir, "logs").getCanonicalFile();
            File target = new File(logsDir, "latest.log").getCanonicalFile();

            // 路径安全校验：目标文件必须在 logs/ 目录内
            String logsPath = logsDir.getCanonicalPath();
            String targetPath = target.getCanonicalPath();
            if (!targetPath.startsWith(logsPath + File.separator)) {
                callback.accept(false, "Log path escaped logs dir");
                return;
            }

            if (!target.exists() || !target.isFile()) {
                callback.accept(false, "Log file not found: " + targetPath);
                return;
            }

            Deque<String> ring = new ArrayDeque<>(lineLimit);
            int scanned = 0;
            int matched = 0;
            try (BufferedReader reader = Files.newBufferedReader(target.toPath(), StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    scanned++;
                    if (keyword != null && !line.toLowerCase().contains(keyword)) continue;
                    if (ring.size() == lineLimit) ring.pollFirst();
                    ring.addLast(line);
                    matched++;
                }
            }

            if (ring.isEmpty()) {
                callback.accept(true, keyword != null
                    ? "没有日志行匹配关键字: " + keyword + "（已扫描 " + scanned + " 行）"
                    : "日志文件为空");
                return;
            }

            StringBuilder sb = new StringBuilder();
            sb.append("# latest.log 最后 ").append(ring.size()).append(" 行");
            if (keyword != null) sb.append("（关键字: ").append(keyword).append("，共匹配 ").append(matched).append(" 行）");
            sb.append('\n');

            int emitted = 0;
            boolean truncated = false;
            for (String l : ring) {
                if (sb.length() + l.length() + 1 > MAX_OUTPUT_CHARS) {
                    truncated = true;
                    break;
                }
                sb.append(l).append('\n');
                emitted++;
            }
            if (truncated) {
                sb.append("... (输出超长已截断，返回了前 ").append(emitted)
                  .append("/").append(ring.size()).append(" 行)");
            }
            callback.accept(true, sb.toString());
        } catch (IOException e) {
            LOGGER.error("Failed to read log file", e);
            callback.accept(false, "Error reading log: " + e.getMessage());
        }
    }
}
