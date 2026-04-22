package com.mcadmin.mod.commands;

import com.mcadmin.mod.ai.AiSession;
import com.mcadmin.mod.ai.AiSessionManager;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.builder.LiteralArgumentBuilder;
import com.mojang.brigadier.suggestion.SuggestionProvider;
import net.minecraft.ChatFormatting;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.SharedSuggestionProvider;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;

public final class AiCommand {
    private static final SuggestionProvider<CommandSourceStack> MODEL_TIERS =
        (ctx, b) -> SharedSuggestionProvider.suggest(new String[]{"flash", "standard", "pro"}, b);
    private static final SuggestionProvider<CommandSourceStack> AGENT_MODES =
        (ctx, b) -> SharedSuggestionProvider.suggest(new String[]{"execute", "query"}, b);

    private AiCommand() {}

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        LiteralArgumentBuilder<CommandSourceStack> root = Commands.literal("ai")
            .requires(src -> src.hasPermission(2))
            .then(Commands.literal("open").executes(AiCommand::openChat))
            .then(Commands.literal("stop").executes(AiCommand::stopChat))
            .then(Commands.literal("status").executes(AiCommand::status))
            .then(Commands.literal("model")
                .then(Commands.argument("tier", StringArgumentType.word())
                    .suggests(MODEL_TIERS)
                    .executes(ctx -> setModel(ctx.getSource(), StringArgumentType.getString(ctx, "tier")))))
            .then(Commands.literal("agent")
                .then(Commands.argument("mode", StringArgumentType.word())
                    .suggests(AGENT_MODES)
                    .executes(ctx -> setAgent(ctx.getSource(), StringArgumentType.getString(ctx, "mode")))));

        dispatcher.register(root);
    }

    private static ServerPlayer requirePlayer(CommandSourceStack src) throws com.mojang.brigadier.exceptions.CommandSyntaxException {
        return src.getPlayerOrException();
    }

    private static int openChat(com.mojang.brigadier.context.CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = requirePlayer(ctx.getSource());
            AiSession session = AiSessionManager.get(player.getUUID());
            session.setChatModeActive(true);
            ctx.getSource().sendSuccess(() -> Component.literal("[AI] 已进入对话模式，聊天消息将发送给 AI。使用 /ai stop 退出。")
                .withStyle(ChatFormatting.AQUA), false);
            return 1;
        } catch (Exception e) {
            ctx.getSource().sendFailure(Component.literal("仅玩家可用"));
            return 0;
        }
    }

    private static int stopChat(com.mojang.brigadier.context.CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = requirePlayer(ctx.getSource());
            AiSession session = AiSessionManager.get(player.getUUID());
            session.setChatModeActive(false);
            ctx.getSource().sendSuccess(() -> Component.literal("[AI] 已退出对话模式").withStyle(ChatFormatting.GRAY), false);
            return 1;
        } catch (Exception e) {
            ctx.getSource().sendFailure(Component.literal("仅玩家可用"));
            return 0;
        }
    }

    private static int status(com.mojang.brigadier.context.CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = requirePlayer(ctx.getSource());
            AiSession s = AiSessionManager.get(player.getUUID());
            String state = s.isChatModeActive() ? "对话中" : "未激活";
            String mode = s.getAgentMode() == AiSession.AgentMode.QUERY_ONLY ? "仅查询" : "执行";
            ctx.getSource().sendSuccess(() -> Component.literal(
                String.format("[AI] 状态=%s  模型=%s  模式=%s", state, s.getModelTier().wire(), mode))
                .withStyle(ChatFormatting.AQUA), false);
            return 1;
        } catch (Exception e) {
            ctx.getSource().sendFailure(Component.literal("仅玩家可用"));
            return 0;
        }
    }

    private static int setModel(CommandSourceStack src, String tier) {
        try {
            ServerPlayer player = requirePlayer(src);
            AiSession s = AiSessionManager.get(player.getUUID());
            s.setModelTier(AiSession.ModelTier.parse(tier));
            src.sendSuccess(() -> Component.literal("[AI] 模型已切换为 " + s.getModelTier().wire())
                .withStyle(ChatFormatting.AQUA), false);
            return 1;
        } catch (Exception e) {
            src.sendFailure(Component.literal("仅玩家可用"));
            return 0;
        }
    }

    private static int setAgent(CommandSourceStack src, String mode) {
        try {
            ServerPlayer player = requirePlayer(src);
            AiSession s = AiSessionManager.get(player.getUUID());
            AiSession.AgentMode parsed;
            switch (mode.toLowerCase()) {
                case "query":
                case "query_only":
                case "readonly":
                    parsed = AiSession.AgentMode.QUERY_ONLY;
                    break;
                default:
                    parsed = AiSession.AgentMode.EXECUTE;
            }
            s.setAgentMode(parsed);
            String label = parsed == AiSession.AgentMode.QUERY_ONLY ? "仅查询" : "执行";
            src.sendSuccess(() -> Component.literal("[AI] 智能体模式已切换为 " + label)
                .withStyle(ChatFormatting.AQUA), false);
            return 1;
        } catch (Exception e) {
            src.sendFailure(Component.literal("仅玩家可用"));
            return 0;
        }
    }
}
