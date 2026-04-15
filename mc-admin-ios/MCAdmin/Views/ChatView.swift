import SwiftUI

struct ChatView: View {
    @Environment(AppState.self) private var appState

    @State private var inputText = ""
    @FocusState private var isInputFocused: Bool

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                VStack(spacing: 0) {
                    // 模式指示器
                    modeBar

                    // 消息列表
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(spacing: 12) {
                                ForEach(appState.chatMessages) { msg in
                                    MessageBubble(message: msg) { pendingId, action in
                                        Task { await appState.confirmCommand(pendingId: pendingId, action: action) }
                                    }
                                    .id(msg.id)
                                }
                            }
                            .padding()
                        }
                        .onChange(of: appState.chatMessages.count) {
                            if let last = appState.chatMessages.last {
                                withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                            }
                        }
                    }

                    // 输入框
                    inputBar
                }
            }
            .navigationTitle("AI 助手")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    // MARK: - 模式栏

    private var modeBar: some View {
        HStack(spacing: 12) {
            // 仅查询模式
            Button {
                appState.toggleQueryOnlyMode()
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: appState.queryOnlyMode ? "eye" : "play.circle")
                        .font(.caption)
                    Text(appState.queryOnlyMode ? "仅查询" : "执行模式")
                        .font(.caption)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(appState.queryOnlyMode ? Theme.orange.opacity(0.2) : Theme.green.opacity(0.2))
                .foregroundStyle(appState.queryOnlyMode ? Theme.orange : Theme.green)
                .cornerRadius(8)
            }

            // 模型选择
            Menu {
                Button("自动") { appState.setModelTier(nil) }
                ForEach(ModelTier.allCases, id: \.self) { tier in
                    Button(tier.displayName) { appState.setModelTier(tier) }
                }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "cpu")
                        .font(.caption)
                    Text(appState.modelTier?.displayName ?? "自动")
                        .font(.caption)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Theme.primary.opacity(0.2))
                .foregroundStyle(Theme.primary)
                .cornerRadius(8)
            }

            Spacer()

            // WebSocket状态
            HStack(spacing: 4) {
                Circle()
                    .fill(appState.wsManager.isConnected ? Theme.online : Theme.red)
                    .frame(width: 6, height: 6)
                Text(appState.wsManager.isConnected ? "已连接" : "未连接")
                    .font(.caption2)
                    .foregroundStyle(Theme.textMuted)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Theme.cardBackground)
    }

    // MARK: - 输入框

    private var inputBar: some View {
        HStack(spacing: 12) {
            TextField("输入消息...", text: $inputText, axis: .vertical)
                .lineLimit(1...5)
                .textFieldStyle(.plain)
                .padding(10)
                .background(Theme.cardBackground)
                .cornerRadius(20)
                .foregroundStyle(Theme.textPrimary)
                .focused($isInputFocused)

            Button {
                let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !text.isEmpty else { return }
                inputText = ""
                isInputFocused = false
                Task { await appState.sendMessage(text) }
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.title2)
                    .foregroundStyle(
                        inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            ? Theme.textDisabled : Theme.primary
                    )
            }
            .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || appState.isLoading)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Theme.background)
    }
}

// MARK: - 消息气泡

struct MessageBubble: View {
    let message: ChatMessage
    let onConfirm: (String, String) -> Void

    var body: some View {
        HStack {
            if message.isUser { Spacer(minLength: 60) }

            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 6) {
                Text(message.content)
                    .font(.body)
                    .foregroundStyle(Theme.textPrimary)
                    .padding(12)
                    .background(message.isUser ? Theme.primary : Theme.cardBackground)
                    .cornerRadius(16)

                // 审核卡片
                if let review = message.review, review.isPending {
                    ReviewCard(review: review, onConfirm: onConfirm)
                }

                // 时间戳
                Text(formatTime(message.timestamp))
                    .font(.caption2)
                    .foregroundStyle(Theme.textMuted)
            }

            if !message.isUser { Spacer(minLength: 60) }
        }
    }

    private func formatTime(_ ms: TimeInterval) -> String {
        let date = Date(timeIntervalSince1970: ms / 1000)
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: date)
    }
}

// MARK: - 审核卡片

struct ReviewCard: View {
    let review: ReviewInfo
    let onConfirm: (String, String) -> Void

    @State private var remainingSeconds: Int

    init(review: ReviewInfo, onConfirm: @escaping (String, String) -> Void) {
        self.review = review
        self.onConfirm = onConfirm
        self._remainingSeconds = State(initialValue: review.expires_in ?? 120)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // 风险等级
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(riskColor)
                Text("需要确认")
                    .font(.subheadline.bold())
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                Text("\(remainingSeconds)s")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(Theme.textMuted)
            }

            if let command = review.command {
                Text(command)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(Theme.orange)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.black.opacity(0.3))
                    .cornerRadius(6)
            }

            if let reason = review.reason {
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
            }

            if let pendingId = review.pending_id {
                HStack(spacing: 12) {
                    Button {
                        onConfirm(pendingId, "approve")
                    } label: {
                        Text("确认执行")
                            .font(.subheadline.bold())
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                            .background(Theme.green)
                            .foregroundStyle(.white)
                            .cornerRadius(8)
                    }

                    Button {
                        onConfirm(pendingId, "reject")
                    } label: {
                        Text("取消")
                            .font(.subheadline.bold())
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                            .background(Theme.red.opacity(0.2))
                            .foregroundStyle(Theme.red)
                            .cornerRadius(8)
                    }
                }
            }
        }
        .padding(12)
        .background(riskColor.opacity(0.1))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(riskColor.opacity(0.3), lineWidth: 1)
        )
        .cornerRadius(12)
        .onAppear { startCountdown() }
    }

    private var riskColor: Color {
        switch review.risk_level {
        case "high": return Theme.red
        case "medium": return Theme.orange
        default: return Theme.green
        }
    }

    private func startCountdown() {
        Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { timer in
            if remainingSeconds > 0 {
                remainingSeconds -= 1
            } else {
                timer.invalidate()
            }
        }
    }
}
