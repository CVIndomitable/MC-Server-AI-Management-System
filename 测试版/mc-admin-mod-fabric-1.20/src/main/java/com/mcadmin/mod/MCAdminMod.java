package com.mcadmin.mod;

import com.mcadmin.mod.ai.AiChatBridge;
import com.mcadmin.mod.commands.AiCommand;
import com.mcadmin.mod.events.ChatInterceptor;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.message.v1.ServerMessageEvents;
import net.minecraft.server.MinecraftServer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class MCAdminMod implements ModInitializer {
    public static final String MOD_ID = "mcadmin";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    private static MCAdminMod instance;
    private WebSocketManager wsManager;
    private StatusReporter statusReporter;
    private CommandExecutor commandExecutor;
    private LogCollector logCollector;
    private AiChatBridge aiChatBridge;
    private ChatInterceptor chatInterceptor;

    @Override
    public void onInitialize() {
        instance = this;

        // 注册网络包
        com.mcadmin.mod.network.TpsPayload.registerCommon();

        CommandRegistrationCallback.EVENT.register((dispatcher, registryAccess, environment) -> {
            AiCommand.register(dispatcher);
        });

        ServerLifecycleEvents.SERVER_STARTED.register(this::onServerStarted);
        ServerLifecycleEvents.SERVER_STOPPING.register(this::onServerStopping);

        LOGGER.info("MC Admin Mod initialized");
    }

    private void onServerStarted(MinecraftServer server) {
        if (!server.isDedicatedServer()) {
            LOGGER.info("Integrated server detected, skipping MC Admin server components");
            return;
        }

        LOGGER.info("Server started, initializing MC Admin components");

        commandExecutor = new CommandExecutor(server);
        statusReporter = new StatusReporter(server);
        logCollector = new LogCollector(statusReporter);
        logCollector.register();

        wsManager = new WebSocketManager(commandExecutor, statusReporter);

        aiChatBridge = new AiChatBridge(server, wsManager);
        wsManager.setAiChatBridge(aiChatBridge);
        chatInterceptor = new ChatInterceptor(aiChatBridge);

        ServerMessageEvents.CHAT_MESSAGE.register(chatInterceptor::onChatMessage);

        wsManager.connect();

        LOGGER.info("MC Admin Mod fully initialized");
    }

    private void onServerStopping(MinecraftServer server) {
        LOGGER.info("Server stopping, cleaning up MC Admin components");

        if (aiChatBridge != null) {
            aiChatBridge.stop();
        }

        if (logCollector != null) {
            logCollector.unregister();
        }

        if (wsManager != null) {
            wsManager.disconnect();
        }

        if (statusReporter != null) {
            statusReporter.stop();
        }
    }

    public static MCAdminMod getInstance() {
        return instance;
    }

    public WebSocketManager getWsManager() {
        return wsManager;
    }
}
