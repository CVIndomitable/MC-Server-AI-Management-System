package com.mcadmin.mod;

import com.google.gson.JsonObject;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.File;
import java.io.IOException;
import java.util.HashSet;
import java.util.Set;
import java.util.function.BiConsumer;

public class CommandExecutor {
    private static final Logger LOGGER = LoggerFactory.getLogger(CommandExecutor.class);

    private final MinecraftServer server;
    private final Set<String> allowedCommands;
    private final Set<String> dangerousCommands;

    public CommandExecutor(MinecraftServer server) {
        this.server = server;
        this.allowedCommands = new HashSet<>(Config.getAllowedCommands());
        this.dangerousCommands = new HashSet<>(Config.getDangerousCommands());
        LOGGER.info("Command whitelist loaded: {}", allowedCommands);
        LOGGER.info("Dangerous commands: {}", dangerousCommands);
    }

    /**
     * 动态更新命令白名单（由服务器下发）
     */
    public void updateAllowedCommands(Set<String> commands) {
        allowedCommands.clear();
        allowedCommands.addAll(commands);
        LOGGER.info("Command whitelist updated: {}", allowedCommands);
    }

    /**
     * 判断指令是否属于危险操作（需要二次确认）
     */
    public boolean isDangerousAction(String action, JsonObject payload) {
        if ("restart".equals(action)) return true;
        if ("execute".equals(action) && payload != null && payload.has("command")) {
            String cmd = payload.get("command").getAsString();
            if (cmd.startsWith("/")) cmd = cmd.substring(1);
            String baseCmd = cmd.split(" ")[0];
            return dangerousCommands.contains(baseCmd);
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

    private void executeMinecraftCommand(JsonObject payload, BiConsumer<Boolean, String> callback) {
        String command = payload.get("command").getAsString();

        // 移除开头的 /
        if (command.startsWith("/")) {
            command = command.substring(1);
        }

        // 检查命令白名单
        String baseCommand = command.split(" ")[0];
        if (!allowedCommands.contains(baseCommand)) {
            callback.accept(false, "Command not allowed: " + baseCommand
                + " (whitelist: " + allowedCommands + ")");
            return;
        }

        LOGGER.info("Executing command: /{}", command);

        try {
            CommandSourceStack source = server.createCommandSourceStack();
            server.getCommands().performPrefixedCommand(source, command);
            callback.accept(true, "Command executed successfully: /" + baseCommand);
        } catch (Exception e) {
            LOGGER.error("Command execution error", e);
            callback.accept(false, "Error: " + e.getMessage());
        }
    }

    private void kickPlayer(JsonObject payload, BiConsumer<Boolean, String> callback) {
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
            // 有配置重启脚本：先执行脚本，再停止服务器
            File scriptFile = new File(restartScript);
            if (!scriptFile.exists()) {
                callback.accept(false, "Restart script not found: " + restartScript);
                return;
            }

            LOGGER.warn("Server restart requested - executing restart script: {}", restartScript);
            callback.accept(true, "Server restarting via script");

            try {
                new ProcessBuilder(restartScript)
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
