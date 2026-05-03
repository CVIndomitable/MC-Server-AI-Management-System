package com.mcadmin.mod.client;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.util.List;

/**
 * 游戏内 AI 对话界面。
 * 半透明背景 + 聊天历史 + 输入框 + 连接状态指示。
 */
public class AiChatScreen extends Screen {
    private static final int HEADER_HEIGHT = 16;
    private static final int INPUT_HEIGHT = 20;
    private static final int PADDING = 6;
    private static final int STATUS_HEIGHT = 12;
    private static final int SCROLL_SPEED = 20;

    private EditBox inputField;
    private int chatAreaTop;
    private int chatAreaBottom;
    private int chatAreaLeft;
    private int chatAreaWidth;
    private int scrollOffset = 0;
    private int maxScroll = 0;
    private boolean isConnected = false;

    private final ClientAiChat aiChat = ClientAiChat.getInstance();
    private final ClientAiChat.ChatListener chatListener = new ClientAiChat.ChatListener() {
        @Override
        public void onMessageAdded(ClientAiChat.ChatMessage message) {
            // 新消息来了，滚动到底部
            scrollOffset = 0;
        }

        @Override
        public void onConnectionStateChanged(boolean connected) {
            isConnected = connected;
        }
    };

    public AiChatScreen() {
        super(Component.literal("AI Chat"));
    }

    @Override
    protected void init() {
        aiChat.addListener(chatListener);
        isConnected = aiChat.isConnected();

        int screenWidth = this.width;
        int screenHeight = this.height;

        // 聊天区域占屏幕 60% 高度，居中
        int panelWidth = Math.min(screenWidth - 40, 500);
        int panelLeft = (screenWidth - panelWidth) / 2;
        int panelHeight = (int) (screenHeight * 0.6f);
        int panelTop = (screenHeight - panelHeight) / 2;

        chatAreaTop = panelTop + HEADER_HEIGHT + PADDING;
        chatAreaBottom = panelTop + panelHeight - INPUT_HEIGHT - STATUS_HEIGHT - PADDING * 3;
        chatAreaLeft = panelLeft + PADDING;
        chatAreaWidth = panelWidth - PADDING * 2;

        // 输入框
        int inputY = panelTop + panelHeight - INPUT_HEIGHT - STATUS_HEIGHT - PADDING;
        inputField = new EditBox(
            this.font, chatAreaLeft, inputY,
            chatAreaWidth, INPUT_HEIGHT,
            Component.literal("")
        );
        inputField.setMaxLength(500);
        inputField.setCanLoseFocus(false);
        addRenderableWidget(inputField);
        setInitialFocus(inputField);
    }

    @Override
    public void render(GuiGraphics gui, int mouseX, int mouseY, float partialTick) {
        // 背景遮罩
        renderBackground(gui, mouseX, mouseY, partialTick);

        int screenWidth = this.width;
        int screenHeight = this.height;
        int panelWidth = Math.min(screenWidth - 40, 500);
        int panelLeft = (screenWidth - panelWidth) / 2;
        int panelHeight = (int) (screenHeight * 0.6f);
        int panelTop = (screenHeight - panelHeight) / 2;

        // 面板背景
        gui.fill(panelLeft, panelTop, panelLeft + panelWidth, panelTop + panelHeight, 0xCC000000);
        gui.renderOutline(panelLeft, panelTop, panelWidth, panelHeight, 0xFF555555);

        // 标题栏
        String title = "AI Chat";
        int titleWidth = this.font.width(title);
        gui.drawString(this.font, title,
            panelLeft + (panelWidth - titleWidth) / 2,
            panelTop + 4, 0xFFFFFFFF, false);

        // 聊天区域裁剪
        gui.enableScissor(chatAreaLeft, chatAreaTop, chatAreaLeft + chatAreaWidth, chatAreaBottom);

        List<ClientAiChat.ChatMessage> messages = aiChat.getMessageHistory();
        int lineHeight = this.font.lineHeight + 2;
        int y = chatAreaBottom - lineHeight;

        synchronized (messages) {
            // 计算需要跳过的行数（从底部向上）
            int skipLines = -scrollOffset;
            int drawnLines = 0;

            for (int i = messages.size() - 1; i >= 0; i--) {
                ClientAiChat.ChatMessage msg = messages.get(i);

                // 消息可能会换行
                var lines = this.font.split(
                    formatMessage(msg),
                    chatAreaWidth - 4
                );

                for (int li = lines.size() - 1; li >= 0; li--) {
                    if (skipLines > 0) {
                        skipLines--;
                        continue;
                    }
                    int color = switch (msg.sender()) {
                        case PLAYER -> 0xFFFFFFFF;
                        case AI -> 0xFF55FFFF;
                        case SYSTEM -> 0xFF888888;
                    };
                    gui.drawString(this.font, lines.get(li),
                        chatAreaLeft + 2, y, color, false);
                    y -= lineHeight;
                    drawnLines++;
                    if (y < chatAreaTop) break;
                }
                if (y < chatAreaTop) break;
            }

            // 计算最大滚动量
            int totalLines = 0;
            for (ClientAiChat.ChatMessage msg : messages) {
                totalLines += this.font.split(formatMessage(msg), chatAreaWidth - 4).size();
            }
            int visibleLines = (chatAreaBottom - chatAreaTop) / lineHeight;
            maxScroll = Math.max(0, totalLines - visibleLines);
        }

        gui.disableScissor();

        // 连接状态
        String status;
        int statusColor;
        if (isConnected) {
            status = "● 已连接";
            statusColor = 0xFF55FF55;
        } else {
            status = "● 未连接";
            statusColor = 0xFFFF5555;
        }
        int statusY = chatAreaBottom + 4;
        gui.drawString(this.font, status, chatAreaLeft, statusY, statusColor, false);

        // 输入框
        inputField.render(gui, mouseX, mouseY, partialTick);

        // 提示文字（输入框为空时）
        if (inputField.getValue().isEmpty() && !inputField.isFocused()) {
            gui.drawString(this.font, "输入消息，按 Enter 发送…",
                inputField.getX() + 4, inputField.getY() + 5, 0xFF888888, false);
        }
    }

    private Component formatMessage(ClientAiChat.ChatMessage msg) {
        String prefix = switch (msg.sender()) {
            case PLAYER -> "[You] ";
            case AI -> "[AI] ";
            case SYSTEM -> "";
        };
        return Component.literal(prefix + msg.text());
    }

    @Override
    public boolean keyPressed(int keyCode, int scanCode, int modifiers) {
        if (keyCode == 256) { // Escape
            this.onClose();
            return true;
        }
        if (keyCode == 257 || keyCode == 335) { // Enter or NumPad Enter
            String text = inputField.getValue().trim();
            if (!text.isEmpty()) {
                aiChat.sendMessage(text);
                inputField.setValue("");
            }
            return true;
        }
        return inputField.keyPressed(keyCode, scanCode, modifiers);
    }

    @Override
    public boolean charTyped(char codePoint, int modifiers) {
        return inputField.charTyped(codePoint, modifiers);
    }

    @Override
    public boolean mouseScrolled(double mouseX, double mouseY, double scrollX, double scrollY) {
        if (mouseX >= chatAreaLeft && mouseX <= chatAreaLeft + chatAreaWidth
            && mouseY >= chatAreaTop && mouseY <= chatAreaBottom) {
            scrollOffset += (int) (scrollY * SCROLL_SPEED / 10.0);
            scrollOffset = Math.max(0, Math.min(scrollOffset, maxScroll));
            return true;
        }
        return super.mouseScrolled(mouseX, mouseY, scrollX, scrollY);
    }

    @Override
    public void removed() {
        aiChat.removeListener(chatListener);
    }

    @Override
    public boolean isPauseScreen() {
        return false;
    }

    @Override
    public void onClose() {
        this.minecraft.setScreen(null);
    }
}
