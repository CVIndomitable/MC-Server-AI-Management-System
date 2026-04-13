package com.mcadmin.mod;

import org.apache.logging.log4j.Level;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.core.LogEvent;
import org.apache.logging.log4j.core.Logger;
import org.apache.logging.log4j.core.appender.AbstractAppender;
import org.apache.logging.log4j.core.config.Property;

/**
 * 自动拦截 WARN/ERROR 级别日志，转发给 StatusReporter
 * 替代手动 addError() 收集方式
 */
public class LogCollector extends AbstractAppender {
    private final StatusReporter statusReporter;

    public LogCollector(StatusReporter statusReporter) {
        super("MCAdminLogCollector", null, null, false, Property.EMPTY_ARRAY);
        this.statusReporter = statusReporter;
    }

    @Override
    public void append(LogEvent event) {
        if (event.getLevel().isMoreSpecificThan(Level.WARN)) {
            String loggerName = event.getLoggerName();
            // 排除自身日志，避免递归
            if (loggerName != null && loggerName.startsWith("com.mcadmin")) {
                return;
            }
            String message = "[" + event.getLevel() + "] "
                + event.getMessage().getFormattedMessage();
            statusReporter.addError(message);
        }
    }

    /**
     * 注册到 Log4j2 根 Logger
     */
    public void register() {
        start();
        Logger rootLogger = (Logger) LogManager.getRootLogger();
        rootLogger.addAppender(this);
        MCAdminMod.LOGGER.info("Log collector registered");
    }

    /**
     * 从根 Logger 移除
     */
    public void unregister() {
        Logger rootLogger = (Logger) LogManager.getRootLogger();
        rootLogger.removeAppender(this);
        stop();
        MCAdminMod.LOGGER.info("Log collector unregistered");
    }
}
