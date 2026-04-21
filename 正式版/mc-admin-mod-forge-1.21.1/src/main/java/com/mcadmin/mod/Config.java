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

    // 环境变量/系统属性覆盖：生产环境推荐用这些而不是明文 properties 文件
    private static final String ENV_WS_URL = "MCADMIN_WS_URL";
    private static final String ENV_WS_TOKEN = "MCADMIN_WS_TOKEN";
    private static final String ENV_SERVER_ID = "MCADMIN_SERVER_ID";
    private static final String PROP_WS_URL = "mcadmin.ws.url";
    private static final String PROP_WS_TOKEN = "mcadmin.ws.token";
    private static final String PROP_SERVER_ID = "mcadmin.server.id";

    private static final String DEFAULT_WS_URL = "wss://your-server-address/mc-admin/ws/mod";
    private static final String DEFAULT_WS_TOKEN = "change-me-in-config-file";

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
        } catch (IOException e) {
            LOGGER.warn("Config file not found, using defaults");
            setDefaults();
            saveConfig();
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
        props.setProperty("ws.url", DEFAULT_WS_URL);
        props.setProperty("ws.token", DEFAULT_WS_TOKEN);
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

    /**
     * 读取覆盖链：系统属性（-D）→ 环境变量 → properties 文件 → 默认值。
     * 生产环境推荐通过 env/系统属性注入敏感配置，避免写入明文文件。
     */
    private static String resolve(String sysProp, String envVar, String propKey, String fallback) {
        String fromSys = System.getProperty(sysProp);
        if (fromSys != null && !fromSys.isEmpty()) return fromSys;
        String fromEnv = System.getenv(envVar);
        if (fromEnv != null && !fromEnv.isEmpty()) return fromEnv;
        return props.getProperty(propKey, fallback);
    }

    public static String getWsUrl() {
        String url = resolve(PROP_WS_URL, ENV_WS_URL, "ws.url", DEFAULT_WS_URL);
        if (url.startsWith("ws://")) {
            LOGGER.warn("WebSocket URL uses plaintext ws://; token will traverse network unencrypted. " +
                "Switch to wss:// in production (override via env {} or system property -D{}).", ENV_WS_URL, PROP_WS_URL);
        }
        return url;
    }

    public static String getAuthToken() {
        return resolve(PROP_WS_TOKEN, ENV_WS_TOKEN, "ws.token", DEFAULT_WS_TOKEN);
    }

    public static String getServerId() {
        String override = resolve(PROP_SERVER_ID, ENV_SERVER_ID, "server.id", null);
        return override != null ? override : props.getProperty("server.id");
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
