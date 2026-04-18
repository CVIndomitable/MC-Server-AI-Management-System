package com.mcadmin.mod;

import com.mcadmin.mod.ai.AiChatBridge;
import com.mcadmin.mod.commands.AiCommand;
import com.mcadmin.mod.events.ChatInterceptor;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import net.neoforged.neoforge.event.server.ServerStartedEvent;
import net.neoforged.neoforge.event.server.ServerStoppingEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Mod("mcadmin")
public class MCAdminMod {
    public static final String MOD_ID = "mcadmin";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    private static MCAdminMod instance;
    private WebSocketManager wsManager;
    private StatusReporter statusReporter;
    private CommandExecutor commandExecutor;
    private LogCollector logCollector;
    private AiChatBridge aiChatBridge;
    private ChatInterceptor chatInterceptor;

    public MCAdminMod(IEventBus modEventBus) {
        instance = this;

        NeoForge.EVENT_BUS.addListener(this::onServerStarted);
        NeoForge.EVENT_BUS.addListener(this::onServerStopping);
        NeoForge.EVENT_BUS.addListener(this::onRegisterCommands);

        LOGGER.info("MC Admin Mod initialized");
    }

    private void onServerStarted(ServerStartedEvent event) {
        // 仅在专用服务器（dedicated server）上启用服务端组件；
        // 否则装了模组的客户端进入单人世界时也会尝试连后端 WebSocket
        if (!event.getServer().isDedicatedServer()) {
            LOGGER.info("Integrated server detected, skipping MC Admin server components");
            return;
        }

        LOGGER.info("Server started, initializing MC Admin components");

        // 初始化指令执行器
        commandExecutor = new CommandExecutor(event.getServer());

        // 初始化状态上报器
        statusReporter = new StatusReporter(event.getServer());

        // 初始化日志收集器（自动拦截 WARN/ERROR 级别日志）
        logCollector = new LogCollector(statusReporter);
        logCollector.register();

        // 初始化 WebSocket 管理器
        wsManager = new WebSocketManager(commandExecutor, statusReporter);

        // AI 对话桥接 + 聊天拦截
        aiChatBridge = new AiChatBridge(event.getServer(), wsManager);
        wsManager.setAiChatBridge(aiChatBridge);
        chatInterceptor = new ChatInterceptor(aiChatBridge);
        NeoForge.EVENT_BUS.register(chatInterceptor);

        wsManager.connect();

        LOGGER.info("MC Admin Mod fully initialized");
    }

    private void onServerStopping(ServerStoppingEvent event) {
        LOGGER.info("Server stopping, cleaning up MC Admin components");

        if (chatInterceptor != null) {
            try {
                NeoForge.EVENT_BUS.unregister(chatInterceptor);
            } catch (Exception ignored) {}
        }

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

    private void onRegisterCommands(RegisterCommandsEvent event) {
        AiCommand.register(event.getDispatcher());
    }

    public static MCAdminMod getInstance() {
        return instance;
    }

    public WebSocketManager getWsManager() {
        return wsManager;
    }
}
