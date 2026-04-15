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
            StringBuilder sb = new StringBuilder();
            sb.append("[").append(event.getLevel()).append("] ")
              .append(event.getMessage().getFormattedMessage());
            // 附加堆栈跟踪前几行（如果有异常）
            Throwable thrown = event.getThrown();
            if (thrown != null) {
                sb.append("\n  ").append(thrown.getClass().getName()).append(": ").append(thrown.getMessage());
                StackTraceElement[] stack = thrown.getStackTrace();
                int lines = Math.min(stack.length, 3);
                for (int i = 0; i < lines; i++) {
                    sb.append("\n    at ").append(stack[i]);
                }
                if (stack.length > lines) {
                    sb.append("\n    ... ").append(stack.length - lines).append(" more");
                }
            }
            statusReporter.addError(sb.toString());
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
