package com.mcadmin.mod.ai;

import java.util.UUID;

/**
 * 单玩家在游戏内的 AI 对话状态。
 */
public class AiSession {
    public enum AgentMode {
        EXECUTE,   // 正常执行模式（可触发工具调用）
        QUERY_ONLY // 仅查询模式（只问答、不执行命令）
    }

    public enum ModelTier {
        FLASH, STANDARD, PRO;

        public static ModelTier parse(String s) {
            if (s == null) return STANDARD;
            switch (s.toLowerCase()) {
                case "flash": return FLASH;
                case "pro":   return PRO;
                default:      return STANDARD;
            }
        }

        public String wire() {
            return name().toLowerCase();
        }
    }

    private final UUID playerId;
    private volatile boolean chatModeActive = false;
    private volatile AgentMode agentMode = AgentMode.EXECUTE;
    private volatile ModelTier modelTier = ModelTier.STANDARD;

    public AiSession(UUID playerId) {
        this.playerId = playerId;
    }

    public UUID getPlayerId() { return playerId; }
    public boolean isChatModeActive() { return chatModeActive; }
    public void setChatModeActive(boolean active) { this.chatModeActive = active; }

    public AgentMode getAgentMode() { return agentMode; }
    public void setAgentMode(AgentMode mode) { this.agentMode = mode; }

    public ModelTier getModelTier() { return modelTier; }
    public void setModelTier(ModelTier tier) { this.modelTier = tier; }

    public boolean isQueryOnly() {
        return agentMode == AgentMode.QUERY_ONLY;
    }
}
