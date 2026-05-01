package com.mcadmin.mod;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.*;

public class Config {
    private static final Logger LOGGER = LoggerFactory.getLogger(Config.class);
    private static final String CONFIG_FILE = "config/mcadmin.properties";

    private static final String DEFAULT_ALLOWED_COMMANDS =
        "list,say,op,deop,kick,ban,pardon,whitelist,save-all,time,weather," +
        "gamemode,tp,give,tell,msg,effect,difficulty,gamerule,seed,title,tellraw,stop," +
        "spark";

    private static final String DEFAULT_DANGEROUS_COMMANDS = "ban,op,deop,stop,whitelist,execute";

    private static Properties props = new Properties();

    static {
        loadConfig();
        ensureServerId();
    }

    private static void loadConfig() {
        try (FileInputStream fis = new FileInputStream(CONFIG_FILE)) {
            props.load(fis);
            LOGGER.info("Config loaded from {}", CONFIG_FILE);
            // 加载后也收紧权限，防止历史文件遗留宽松权限
            restrictPermissions(new File(CONFIG_FILE));
            validateConfig();
        } catch (IOException e) {
            LOGGER.warn("Config file not found, using defaults");
            setDefaults();
            saveConfig();
        }
    }

    private static void validateConfig() {
        String wsUrl = getWsUrl();
        if (!wsUrl.startsWith("ws://") && !wsUrl.startsWith("wss://")) {
            LOGGER.error("Invalid ws.url: must start with ws:// or wss://, got: {}", wsUrl);
        }

        String token = getAuthToken();
        if (token.equals("change-me-in-config-file")) {
            LOGGER.warn("ws.token is still set to default value, please update config file");
        }

        long interval = getReportInterval();
        if (interval < 1000 || interval > 60000) {
            LOGGER.warn("status.report_interval out of recommended range (1000-60000ms): {}", interval);
        }
    }

    /**
     * 将配置文件权限收紧为仅属主可读写（POSIX：0600；Windows 回退到 File API）。
     * 配置中含 ws.token 明文，必须防止同机其他用户读取。
     */
    private static void restrictPermissions(File file) {
        if (!file.exists()) return;
        Path path = file.toPath();
        try {
            Set<PosixFilePermission> perms = PosixFilePermissions.fromString("rw-------");
            Files.setPosixFilePermissions(path, perms);
        } catch (UnsupportedOperationException | IOException e) {
            // 非 POSIX 文件系统（如 Windows NTFS），尽力而为
            boolean ok = file.setReadable(false, false)
                      && file.setReadable(true, true)
                      && file.setWritable(false, false)
                      && file.setWritable(true, true);
            if (!ok) {
                LOGGER.warn("Could not restrict config file permissions: {}", file.getAbsolutePath());
            }
        }
    }

    private static void setDefaults() {
        props.setProperty("ws.url", "ws://your-server-address/mc-admin/ws/mod");
        props.setProperty("ws.token", "change-me-in-config-file");
        // server.id 留空，由 ensureServerId() 自动生成
        props.setProperty("server.id", "");
        props.setProperty("server.restart_script", "");
        props.setProperty("status.report_interval", "5000");
        props.setProperty("security.require_confirmation", "false");
        props.setProperty("security.allowed_commands", DEFAULT_ALLOWED_COMMANDS);
        props.setProperty("security.dangerous_commands", DEFAULT_DANGEROUS_COMMANDS);
    }

    /**
     * 确保 server.id 存在，如果为空或未设置则自动生成唯一ID并写回配置文件
     */
    private static void ensureServerId() {
        String currentId = props.getProperty("server.id", "").trim();
        if (currentId.isEmpty()) {
            String generated = "mc_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
            props.setProperty("server.id", generated);
            saveConfig();
            LOGGER.info("Auto-generated server.id: {}", generated);
        }
    }

    /**
     * 将当前配置写回文件
     */
    private static void saveConfig() {
        File configFile = new File(CONFIG_FILE);
        configFile.getParentFile().mkdirs();
        try (FileOutputStream fos = new FileOutputStream(configFile)) {
            props.store(fos, "MCAdmin Mod Configuration");
            LOGGER.info("Config saved to {}", CONFIG_FILE);
        } catch (IOException e) {
            LOGGER.error("Failed to save config: {}", e.getMessage());
        }
        restrictPermissions(configFile);
    }

    public static String getWsUrl() {
        return props.getProperty("ws.url", "ws://your-server-address/mc-admin/ws/mod");
    }

    public static String getAuthToken() {
        return props.getProperty("ws.token", "change-me-in-config-file");
    }

    public static String getServerId() {
        return props.getProperty("server.id");
    }

    public static long getReportInterval() {
        try {
            return Long.parseLong(props.getProperty("status.report_interval", "5000"));
        } catch (NumberFormatException e) {
            LOGGER.warn("Invalid report_interval config, using default 5000ms");
            return 5000L;
        }
    }

    public static boolean requireConfirmation() {
        return Boolean.parseBoolean(props.getProperty("security.require_confirmation", "false"));
    }

    /**
     * 获取允许执行的命令白名单
     */
    public static Set<String> getAllowedCommands() {
        String raw = props.getProperty("security.allowed_commands", DEFAULT_ALLOWED_COMMANDS);
        Set<String> commands = new HashSet<>();
        for (String cmd : raw.split(",")) {
            String trimmed = cmd.trim();
            if (!trimmed.isEmpty()) {
                commands.add(trimmed);
            }
        }
        return commands;
    }

    /**
     * 获取需要二次确认的危险命令列表
     */
    public static Set<String> getDangerousCommands() {
        String raw = props.getProperty("security.dangerous_commands", DEFAULT_DANGEROUS_COMMANDS);
        Set<String> commands = new HashSet<>();
        for (String cmd : raw.split(",")) {
            String trimmed = cmd.trim();
            if (!trimmed.isEmpty()) {
                commands.add(trimmed);
            }
        }
        return commands;
    }

    /**
     * 获取重启脚本路径（空字符串表示未配置）
     */
    public static String getRestartScript() {
        return props.getProperty("server.restart_script", "").trim();
    }
}
