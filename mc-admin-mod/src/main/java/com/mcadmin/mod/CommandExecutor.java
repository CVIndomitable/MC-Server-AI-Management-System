package com.mcadmin.mod;

import com.google.gson.JsonObject;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.HashSet;
import java.util.Set;
import java.util.function.BiConsumer;

public class CommandExecutor {
    private static final Logger LOGGER = LoggerFactory.getLogger(CommandExecutor.class);

    private final MinecraftServer server;
    private final Set<String> allowedCommands;

    public CommandExecutor(MinecraftServer server) {
        this.server = server;
        this.allowedCommands = new HashSet<>();
        initAllowedCommands();
    }

    private void initAllowedCommands() {
        // 白名单命令（可从配置文件加载）
        allowedCommands.add("list");
        allowedCommands.add("say");
        allowedCommands.add("op");
        allowedCommands.add("deop");
        allowedCommands.add("kick");
        allowedCommands.add("ban");
        allowedCommands.add("pardon");
        allowedCommands.add("whitelist");
        allowedCommands.add("save-all");
        allowedCommands.add("time");
        allowedCommands.add("weather");
        allowedCommands.add("gamemode");
        allowedCommands.add("tp");
        allowedCommands.add("give");
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
            callback.accept(false, "Command not allowed: " + baseCommand);
            return;
        }

        LOGGER.info("Executing command: /{}", command);

        try {
            CommandSourceStack source = server.createCommandSourceStack();
            // NeoForge 1.21.1 中 performPrefixedCommand 返回 void
            server.getCommands().performPrefixedCommand(source, command);
            callback.accept(true, "Command executed successfully");
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
        // 重启需要外部脚本支持，这里只是停止服务器
        LOGGER.warn("Server restart requested - stopping server");
        callback.accept(true, "Server stopping for restart");

        server.execute(() -> {
            server.halt(false);
        });
    }
}
