package com.mcadmin.mod.ai;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public final class AiSessionManager {
    private static final Map<UUID, AiSession> SESSIONS = new ConcurrentHashMap<>();

    private AiSessionManager() {}

    public static AiSession get(UUID playerId) {
        return SESSIONS.computeIfAbsent(playerId, AiSession::new);
    }

    public static AiSession getIfExists(UUID playerId) {
        return SESSIONS.get(playerId);
    }

    public static void remove(UUID playerId) {
        SESSIONS.remove(playerId);
    }
}
