import SwiftUI

struct LoginView: View {
    @Environment(AppState.self) private var appState

    @State private var username = ""
    @State private var password = ""
    @State private var showManualLogin = false

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        // Logo区域
                        VStack(spacing: 8) {
                            Image(systemName: "server.rack")
                                .font(.system(size: 60))
                                .foregroundStyle(Theme.primary)
                            Text("MC Server Admin")
                                .font(.title.bold())
                                .foregroundStyle(Theme.textPrimary)
                            Text("AI Minecraft 服务器管理")
                                .font(.subheadline)
                                .foregroundStyle(Theme.textMuted)
                        }
                        .padding(.top, 60)

                        // 已保存账号
                        if !appState.savedAccounts.isEmpty && !showManualLogin {
                            savedAccountsSection
                        }

                        // 手动登录
                        if appState.savedAccounts.isEmpty || showManualLogin {
                            manualLoginSection
                        }

                        // 切换按钮
                        if !appState.savedAccounts.isEmpty {
                            Button(showManualLogin ? "使用已保存账号" : "使用其他账号登录") {
                                withAnimation { showManualLogin.toggle() }
                            }
                            .foregroundStyle(Theme.primary)
                            .font(.subheadline)
                        }

                        // 错误提示
                        if let error = appState.error {
                            Text(error)
                                .font(.caption)
                                .foregroundStyle(Theme.red)
                                .padding(.horizontal)
                        }
                    }
                    .padding()
                }
            }
            .navigationBarHidden(true)
        }
        .task {
            await appState.loadSavedAccounts()
        }
    }

    // MARK: - 已保存账号列表

    private var savedAccountsSection: some View {
        VStack(spacing: 12) {
            Text("选择账号")
                .font(.headline)
                .foregroundStyle(Theme.textSecondary)

            ForEach(appState.savedAccounts) { account in
                Button {
                    Task { await appState.quickLogin(username: account.username) }
                } label: {
                    HStack {
                        Image(systemName: "person.circle.fill")
                            .font(.title2)
                            .foregroundStyle(Theme.primary)
                        Text(account.username)
                            .font(.body)
                            .foregroundStyle(Theme.textPrimary)
                        Spacer()
                        Image(systemName: "chevron.right")
                            .foregroundStyle(Theme.textMuted)
                    }
                    .padding()
                    .background(Theme.cardBackground)
                    .cornerRadius(12)
                }
                .contextMenu {
                    Button(role: .destructive) {
                        Task { await appState.removeSavedAccount(username: account.username) }
                    } label: {
                        Label("移除账号", systemImage: "trash")
                    }
                }
            }
        }
    }

    // MARK: - 手动登录表单

    private var manualLoginSection: some View {
        VStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 8) {
                Text("用户名")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                TextField("", text: $username)
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(Theme.cardBackground)
                    .cornerRadius(8)
                    .foregroundStyle(Theme.textPrimary)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("密码")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                SecureField("", text: $password)
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(Theme.cardBackground)
                    .cornerRadius(8)
                    .foregroundStyle(Theme.textPrimary)
            }

            Button {
                Task {
                    let success = await appState.login(username: username, password: password)
                    if success {
                        password = ""
                    }
                }
            } label: {
                HStack {
                    if appState.isLoading {
                        ProgressView()
                            .tint(.white)
                    }
                    Text("登 录")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(
                    (username.isEmpty || password.isEmpty)
                        ? Theme.primary.opacity(0.5)
                        : Theme.primary
                )
                .foregroundStyle(.white)
                .cornerRadius(12)
            }
            .disabled(username.isEmpty || password.isEmpty || appState.isLoading)
        }
    }
}
