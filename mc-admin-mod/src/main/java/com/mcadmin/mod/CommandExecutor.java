package com.mcadmin.mod;

import com.google.gson.JsonObject;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.File;
import java.io.IOException;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.BiConsumer;

public class CommandExecutor {
    private static final Logger LOGGER = LoggerFactory.getLogger(CommandExecutor.class);

    private final MinecraftServer server;
    // 使用 volatile + 原子替换引用，保证跨线程读写安全
    private volatile Set<String> allowedCommands;
    private volatile Set<String> dangerousCommands;

    public CommandExecutor(MinecraftServer server) {
        this.server = server;
        this.allowedCommands = Collections.unmodifiableSet(new HashSet<>(Config.getAllowedCommands()));
        this.dangerousCommands = Collections.unmodifiableSet(new HashSet<>(Config.getDangerousCommands()));
        LOGGER.info("Command whitelist loaded: {}", allowedCommands);
        LOGGER.info("Dangerous commands: {}", dangerousCommands);
    }

    /**
     * 动态更新命令白名单（由服务器下发）
     * 原子替换引用，避免 clear()+addAll() 窗口期的竞态
     */
    public void updateAllowedCommands(Set<String> commands) {
        this.allowedCommands = Collections.unmodifiableSet(new HashSet<>(commands));
        LOGGER.info("Command whitelist updated: {}", allowedCommands);
    }

    /**
     * 判断指令是否属于危险操作（需要二次确认）
     */
    public boolean isDangerousAction(String action, JsonObject payload) {
        if ("restart".equals(action)) return true;
        if ("execute".equals(action) && payload != null && payload.has("command")) {
            return containsDangerousCommand(payload.get("command").getAsString());
        }
        return false;
    }

    /**
     * 生成指令的可读描述（用于二次确认提示）
     */
    public String describeCommand(String action, JsonObject payload) {
        if ("restart".equals(action)) return "重启服务器";
        if ("execute".equals(action) && payload != null && payload.has("command")) {
            return payload.get("command").getAsString();
        }
        if ("kick_player".equals(action) && payload != null && payload.has("player")) {
            return "踢出玩家 " + payload.get("player").getAsString();
        }
        if ("op_player".equals(action) && payload != null && payload.has("player")) {
            return "给予OP " + payload.get("player").getAsString();
        }
        return action;
    }

    public void executeCommand(String commandId, String action, JsonObject payload, BiConsumer<Boolean, String> callback) {
        // 在服务器主线程执行
        server.execute(() -> {
            try {
                switch (action) {
                    case "execute":
                        executeMinecraftCommand(payload, callback);
                        break;
                    case "kick_player":
                        kickPlayer(payload, callback);
                        break;
                    case "op_player":
                        opPlayer(payload, callback);
                        break;
                    case "restart":
                        restartServer(callback);
                        break;
                    default:
                        callback.accept(false, "Unknown action: " + action);
                }
            } catch (Exception e) {
                LOGGER.error("Command execution failed", e);
                callback.accept(false, "Error: " + e.getMessage());
            }
        });
    }

    /**
     * 递归检查命令是否在白名单中，包括 /execute ... run 嵌套的子命令
     */
    private boolean isCommandAllowed(String command, Set<String> currentAllowed) {
        String cmd = command.startsWith("/") ? command.substring(1) : command;
        String baseCommand = cmd.split(" ")[0];

        if (!currentAllowed.contains(baseCommand)) {
            return false;
        }

        // 检测 execute ... run 嵌套命令
        if ("execute".equals(baseCommand)) {
            String lowerCmd = cmd.toLowerCase();
            int runIdx = lowerCmd.indexOf(" run ");
            if (runIdx >= 0) {
                String subCommand = cmd.substring(runIdx + 5).trim();
                return isCommandAllowed(subCommand, currentAllowed);
            }
        }
        return true;
    }

    /**
     * 递归检查命令是否包含危险子命令
     */
    private boolean containsDangerousCommand(String command) {
        String cmd = command.startsWith("/") ? command.substring(1) : command;
        String baseCommand = cmd.split(" ")[0];
        Set<String> currentDangerous = dangerousCommands;

        if (currentDangerous.contains(baseCommand)) {
            return true;
        }
        // 检测 execute ... run 嵌套
        if ("execute".equals(baseCommand)) {
            String lowerCmd = cmd.toLowerCase();
            int runIdx = lowerCmd.indexOf(" run ");
            if (runIdx >= 0) {
                String subCommand = cmd.substring(runIdx + 5).trim();
                return containsDangerousCommand(subCommand);
            }
        }
        return false;
    }

    private void executeMinecraftCommand(JsonObject payload, BiConsumer<Boolean, String> callback) {
        if (!payload.has("command") || payload.get("command").isJsonNull()) {
            callback.accept(false, "Missing 'command' in payload");
            return;
        }

        String command = payload.get("command").getAsString();

        // 移除开头的 /
        if (command.startsWith("/")) {
            command = command.substring(1);
        }

        // 检查命令白名单，包括嵌套子命令（读取 volatile 引用的快照）
        String baseCommand = command.split(" ")[0];
        Set<String> currentAllowed = allowedCommands;
        if (!isCommandAllowed(command, currentAllowed)) {
            callback.accept(false, "Command not allowed: " + baseCommand
                + " (whitelist: " + currentAllowed + ")");
            return;
        }

        LOGGER.info("Executing command: /{}", command);

        try {
            // 通过 withCallback 捕获命令执行结果
            AtomicBoolean success = new AtomicBoolean(true);
            CommandSourceStack source = server.createCommandSourceStack()
                .withCallback((ok, resultValue) -> {
                    if (!ok) success.set(false);
                });
            server.getCommands().performPrefixedCommand(source, command);
            if (success.get()) {
                callback.accept(true, "Command executed successfully: /" + baseCommand);
            } else {
                callback.accept(false, "Command failed: /" + baseCommand);
            }
        } catch (Exception e) {
            LOGGER.error("Command execution error", e);
            callback.accept(false, "Error: " + e.getMessage());
        }
    }

    private void kickPlayer(JsonObject payload, BiConsumer<Boolean, String> callback) {
        if (!payload.has("player") || payload.get("player").isJsonNull()) {
            callback.accept(false, "Missing 'player' in payload");
            return;
        }
        String playerName = payload.get("player").getAsString();
        String reason = payload.has("reason") ? payload.get("reason").getAsString() : "Kicked by admin";

        ServerPlayer player = server.getPlayerList().getPlayerByName(playerName);
        if (player == null) {
            callback.accept(false, "Player not found: " + playerName);
            return;
        }

        player.connection.disconnect(net.minecraft.network.chat.Component.literal(reason));
        callback.accept(true, "Kicked player: " + playerName);
        LOGGER.info("Kicked player {} (reason: {})", playerName, reason);
    }

    private void opPlayer(JsonObject payload, BiConsumer<Boolean, String> callback) {
        if (!payload.has("player") || payload.get("player").isJsonNull()) {
            callback.accept(false, "Missing 'player' in payload");
            return;
        }
        String playerName = payload.get("player").getAsString();

        ServerPlayer player = server.getPlayerList().getPlayerByName(playerName);
        if (player == null) {
            callback.accept(false, "Player not found: " + playerName);
            return;
        }

        server.getPlayerList().op(player.getGameProfile());
        callback.accept(true, "Made " + playerName + " a server operator");
        LOGGER.info("Opped player {}", playerName);
    }

    private void restartServer(BiConsumer<Boolean, String> callback) {
        String restartScript = Config.getRestartScript();

        if (!restartScript.isEmpty()) {
            File scriptFile = new File(restartScript);

            // 路径安全校验：必须存在、是文件、可执行、在服务器目录下
            try {
                String canonicalPath = scriptFile.getCanonicalPath();
                String serverDir = new File(".").getCanonicalPath();
                if (!canonicalPath.startsWith(serverDir + File.separator)) {
                    callback.accept(false, "Restart script must be within server directory");
                    return;
                }
            } catch (IOException e) {
                callback.accept(false, "Invalid restart script path");
                return;
            }

            if (!scriptFile.exists() || !scriptFile.isFile()) {
                callback.accept(false, "Restart script not found: " + restartScript);
                return;
            }
            if (!scriptFile.canExecute()) {
                callback.accept(false, "Restart script is not executable: " + restartScript);
                return;
            }

            LOGGER.warn("Server restart requested - executing restart script: {}", restartScript);
            callback.accept(true, "Server restarting via script");

            try {
                // 直接执行脚本文件，不通过shell解释器，防止命令注入
                new ProcessBuilder(scriptFile.getCanonicalPath())
                    .inheritIO()
                    .start();
            } catch (IOException e) {
                LOGGER.error("Failed to execute restart script", e);
            }

            server.execute(() -> server.halt(false));
        } else {
            // 无重启脚本：写标志文件 + 停止（外部 watchdog/systemd 可据此自动重启）
            LOGGER.warn("Server restart requested - writing restart flag and stopping");
            try {
                new File(".restart").createNewFile();
            } catch (IOException e) {
                LOGGER.error("Failed to create restart flag file", e);
            }

            callback.accept(true, "Server stopping for restart (restart flag written)");
            server.execute(() -> server.halt(false));
        }
    }
}
