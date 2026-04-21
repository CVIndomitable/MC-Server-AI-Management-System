import SwiftUI

struct ActionsView: View {
    @Environment(AppState.self) private var appState

    @State private var showInputModal = false
    @State private var inputTitle = ""
    @State private var inputPlaceholder = ""
    @State private var inputText = ""
    @State private var inputAction: ((String) -> Void)?
    @State private var showConfirm = false
    @State private var confirmTitle = ""
    @State private var confirmMessage = ""
    @State private var confirmAction: (() -> Void)?

    private let columns = [
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12),
    ]

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                ScrollView {
                    LazyVGrid(columns: columns, spacing: 12) {
                        actionButton(
                            title: "重启服务器",
                            icon: "arrow.clockwise",
                            color: Theme.orange
                        ) {
                            showConfirmDialog(
                                title: "重启服务器",
                                message: "确定要重启服务器吗？所有在线玩家将被断开连接。"
                            ) {
                                sendCommand("请重启服务器")
                            }
                        }

                        actionButton(
                            title: "备份存档",
                            icon: "externaldrive.badge.checkmark",
                            color: Theme.green
                        ) {
                            sendCommand("请备份服务器存档")
                        }

                        actionButton(
                            title: "全服公告",
                            icon: "megaphone",
                            color: Theme.primary
                        ) {
                            showInput(title: "发送公告", placeholder: "输入公告内容") { text in
                                sendCommand("请向全服广播：\(text)")
                            }
                        }

                        actionButton(
                            title: "白名单",
                            icon: "person.badge.plus",
                            color: Theme.cyan
                        ) {
                            showInput(title: "添加白名单", placeholder: "输入玩家名") { text in
                                sendCommand("请将 \(text) 添加到白名单")
                            }
                        }

                        actionButton(
                            title: "关闭服务器",
                            icon: "power",
                            color: Theme.red
                        ) {
                            showConfirmDialog(
                                title: "关闭服务器",
                                message: "确定要关闭服务器吗？这是一个危险操作！"
                            ) {
                                sendCommand("请关闭服务器")
                            }
                        }

                        actionButton(
                            title: "保存世界",
                            icon: "square.and.arrow.down",
                            color: Theme.purple
                        ) {
                            sendCommand("请保存世界")
                        }
                    }
                    .padding()
                }
            }
            .navigationTitle("快捷操作")
            .navigationBarTitleDisplayMode(.inline)
            .alert(confirmTitle, isPresented: $showConfirm) {
                Button("取消", role: .cancel) {}
                Button("确定", role: .destructive) { confirmAction?() }
            } message: {
                Text(confirmMessage)
            }
            .sheet(isPresented: $showInputModal) {
                inputModalView
            }
        }
    }

    // MARK: - 操作按钮

    private func actionButton(title: String, icon: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 12) {
                Image(systemName: icon)
                    .font(.system(size: 28))
                    .foregroundStyle(color)

                Text(title)
                    .font(.subheadline.bold())
                    .foregroundStyle(Theme.textPrimary)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 100)
            .background(Theme.cardBackground)
            .cornerRadius(12)
        }
    }

    // MARK: - 输入弹窗

    private var inputModalView: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                VStack(spacing: 16) {
                    TextField(inputPlaceholder, text: $inputText)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(Theme.cardBackground)
                        .cornerRadius(8)
                        .foregroundStyle(Theme.textPrimary)

                    Button {
                        let text = inputText
                        inputText = ""
                        showInputModal = false
                        inputAction?(text)
                    } label: {
                        Text("发送")
                            .fontWeight(.semibold)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(inputText.isEmpty ? Theme.primary.opacity(0.5) : Theme.primary)
                            .foregroundStyle(.white)
                            .cornerRadius(12)
                    }
                    .disabled(inputText.isEmpty)

                    Spacer()
                }
                .padding()
            }
            .navigationTitle(inputTitle)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") {
                        inputText = ""
                        showInputModal = false
                    }
                    .foregroundStyle(Theme.textSecondary)
                }
            }
        }
        .presentationDetents([.medium])
    }

    // MARK: - 辅助方法

    private func showInput(title: String, placeholder: String, action: @escaping (String) -> Void) {
        inputTitle = title
        inputPlaceholder = placeholder
        inputAction = action
        inputText = ""
        showInputModal = true
    }

    private func showConfirmDialog(title: String, message: String, action: @escaping () -> Void) {
        confirmTitle = title
        confirmMessage = message
        confirmAction = action
        showConfirm = true
    }

    private func sendCommand(_ message: String) {
        Task { await appState.sendMessage(message) }
    }
}
