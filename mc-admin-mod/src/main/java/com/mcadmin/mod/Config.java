package com.mcadmin.mod;

import com.google.gson.JsonObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.FileInputStream;
import java.io.IOException;
import java.util.Properties;

public class Config {
    private static final Logger LOGGER = LoggerFactory.getLogger(Config.class);
    private static final String CONFIG_FILE = "config/mcadmin.properties";

    private static Properties props = new Properties();

    static {
        loadConfig();
    }

    private static void loadConfig() {
        try (FileInputStream fis = new FileInputStream(CONFIG_FILE)) {
            props.load(fis);
            LOGGER.info("Config loaded from {}", CONFIG_FILE);
        } catch (IOException e) {
            LOGGER.warn("Config file not found, using defaults");
            setDefaults();
        }
    }

    private static void setDefaults() {
        props.setProperty("ws.url", "ws://your-server-address/mc-admin/ws/mod");
        props.setProperty("ws.token", "change-me-in-config-file");
        props.setProperty("server.id", "srv_001");
        props.setProperty("status.report_interval", "5000");
        props.setProperty("security.require_confirmation", "true");
    }

    public static String getWsUrl() {
        return props.getProperty("ws.url", "ws://your-server-address/mc-admin/ws/mod");
    }

    public static String getAuthToken() {
        return props.getProperty("ws.token", "change-me-in-config-file");
    }

    public static String getServerId() {
        return props.getProperty("server.id", "srv_001");
    }

    public static long getReportInterval() {
        return Long.parseLong(props.getProperty("status.report_interval", "5000"));
    }

    public static boolean requireConfirmation() {
        return Boolean.parseBoolean(props.getProperty("security.require_confirmation", "true"));
    }
}
