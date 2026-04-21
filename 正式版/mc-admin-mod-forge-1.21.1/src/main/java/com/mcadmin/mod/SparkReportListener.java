package com.mcadmin.mod;

import com.google.gson.JsonObject;
import org.apache.logging.log4j.Level;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.core.LogEvent;
import org.apache.logging.log4j.core.Logger;
import org.apache.logging.log4j.core.appender.AbstractAppender;
import org.apache.logging.log4j.core.config.Property;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 监听 Spark profiler 异步完成输出。
 * profiler start --timeout N 到期后，Spark 会在后台上传 heap dump 并在 console 打印
 * "Profiler Report: https://spark.lucko.me/<id>"。这条消息发生在原始
 * execute_command 返回之后，OutputCapture 已不在现场，因此走日志监听抓取，
 * 然后以 async_event 回推后端。
 */
public class SparkReportListener extends AbstractAppender {
    private static final Pattern REPORT_URL = Pattern.compile("https://spark\\.lucko\\.me/[A-Za-z0-9]+");
    private static final org.slf4j.Logger LOGGER =
        org.slf4j.LoggerFactory.getLogger(SparkReportListener.class);
    // 线程重入保护（SparkReportListener 自身 LOGGER 可能被父类触发）
    private static final ThreadLocal<Boolean> IN_APPEND = ThreadLocal.withInitial(() -> false);

    private final WebSocketManager wsManager;

    public SparkReportListener(WebSocketManager wsManager) {
        super("MCAdminSparkReportListener", null, null, false, Property.EMPTY_ARRAY);
        this.wsManager = wsManager;
    }

    @Override
    public void append(LogEvent event) {
        if (IN_APPEND.get()) return;
        String loggerName = event.getLoggerName();
        // 只关心 Spark 自身日志，避免全量扫描
        if (loggerName == null || !loggerName.startsWith("me.lucko.spark")) {
            return;
        }
        if (event.getLevel() == null || event.getLevel().isLessSpecificThan(Level.DEBUG)) {
            return;
        }
        IN_APPEND.set(true);
        try {
            String text = event.getMessage().getFormattedMessage();
            if (text == null || text.isEmpty()) return;
            Matcher m = REPORT_URL.matcher(text);
            if (!m.find()) return;
            String url = m.group();
            LOGGER.info("Spark profiler report detected: {}", url);
            sendReport(url, text);
        } catch (Exception e) {
            LOGGER.warn("Failed to process spark log event: {}", e.getMessage());
        } finally {
            IN_APPEND.remove();
        }
    }

    private void sendReport(String url, String rawText) {
        if (wsManager == null) return;
        JsonObject msg = new JsonObject();
        msg.addProperty("type", "async_event");
        msg.addProperty("event", "spark_report");
        msg.addProperty("server_id", Config.getServerId());
        msg.addProperty("url", url);
        // 原文截断，避免 WS 消息过大
        String trimmed = rawText.length() > 2000 ? rawText.substring(0, 2000) + "..." : rawText;
        msg.addProperty("text", trimmed);
        msg.addProperty("timestamp", System.currentTimeMillis() / 1000);
        wsManager.sendMessage(msg.toString());
    }

    public void register() {
        start();
        Logger rootLogger = (Logger) LogManager.getRootLogger();
        rootLogger.addAppender(this);
        LOGGER.info("Spark report listener registered");
    }

    public void unregister() {
        Logger rootLogger = (Logger) LogManager.getRootLogger();
        rootLogger.removeAppender(this);
        stop();
        LOGGER.info("Spark report listener unregistered");
    }
}
