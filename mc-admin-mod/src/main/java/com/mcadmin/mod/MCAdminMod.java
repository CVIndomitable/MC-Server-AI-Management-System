package com.mcadmin.mod;

import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.fml.event.lifecycle.FMLDedicatedServerSetupEvent;
import net.neoforged.neoforge.common.NeoForge;
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

    public MCAdminMod(IEventBus modEventBus) {
        instance = this;

        modEventBus.addListener(this::onServerSetup);
        NeoForge.EVENT_BUS.addListener(this::onServerStarted);
        NeoForge.EVENT_BUS.addListener(this::onServerStopping);

        LOGGER.info("MC Admin Mod initialized");
    }

    private void onServerSetup(FMLDedicatedServerSetupEvent event) {
        LOGGER.info("MC Admin Mod server setup");
    }

    private void onServerStarted(ServerStartedEvent event) {
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
        wsManager.connect();

        LOGGER.info("MC Admin Mod fully initialized");
    }

    private void onServerStopping(ServerStoppingEvent event) {
        LOGGER.info("Server stopping, cleaning up MC Admin components");

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
