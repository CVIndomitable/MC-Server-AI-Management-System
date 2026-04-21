import Foundation
import SwiftUI

// MARK: - 全局状态管理

@Observable
final class AppState {
    // 认证状态
    var isAuthenticated = false
    var token: String?
    var username = ""
    var userRole = "" // "admin" | "user"

    // 服务器
    var serverId = ""
    var serverSelected = false
    var myServers: [UserServerInfo] = []
    var unboundServers: [ServerInfo] = []

    // 状态监控
    var serverStatus: ServerStatus?
    var isBackendOnline = false

    // 聊天
    var chatMessages: [ChatMessage] = []

    // UI状态
    var isLoading = false
    var error: String?
    var queryOnlyMode = false
    var modelTier: ModelTier?

    // 当前聊天任务（用于取消）
    var currentChatTask: Task<Void, Never>?

    // 多账号
    var savedAccounts: [SavedAccount] = []

    // WebSocket
    let wsManager = WebSocketManager()

    // 计算属性
    var isAdmin: Bool { userRole == "admin" }

    var currentServerRole: String? {
        myServers.first(where: { $0.server_id == serverId })?.role
    }

    var isServerOwner: Bool {
        currentServerRole == "owner"
    }

    // MARK: - UserDefaults keys

    private enum Keys {
        static let username = "mc_admin_username"
        static let role = "mc_admin_role"
        static let serverId = "mc_admin_server_id"
        static let queryOnly = "mc_admin_query_only"
        static let modelTier = "mc_admin_model_tier"
        static let savedAccounts = "mc_admin_saved_accounts"
    }

    init() {
        setupWSCallbacks()
    }

    // MARK: - 会话恢复

    func restoreSession() async {
        guard let savedToken = KeychainService.load(key: KeychainService.tokenKey) else { return }

        // 检查token是否过期
        guard let payload = JWTPayload.decode(from: savedToken), !payload.isExpired else {
            KeychainService.delete(key: KeychainService.tokenKey)
            return
        }

        token = savedToken
        username = UserDefaults.standard.string(forKey: Keys.username) ?? payload.sub
        userRole = UserDefaults.standard.string(forKey: Keys.role) ?? payload.role
        queryOnlyMode = UserDefaults.standard.bool(forKey: Keys.queryOnly)

        if let tierStr = UserDefaults.standard.string(forKey: Keys.modelTier) {
            modelTier = ModelTier(rawValue: tierStr)
        }

        await APIClient.shared.setToken(savedToken)
        isAuthenticated = true

        // 恢复服务器选择
        if let savedServerId = UserDefaults.standard.string(forKey: Keys.serverId), !savedServerId.isEmpty {
            serverId = savedServerId
        }

        await loadSavedAccounts()
    }

    // MARK: - 登录

    func login(username: String, password: String) async -> Bool {
        isLoading = true
        error = nil

        do {
            let response = try await APIClient.shared.login(username: username, password: password)
            let token = response.access_token

            guard let payload = JWTPayload.decode(from: token) else {
                error = "Token解析失败"
                isLoading = false
                return false
            }

            self.token = token
            self.username = payload.sub
            self.userRole = payload.role
            self.isAuthenticated = true

            // 持久化
            KeychainService.save(key: KeychainService.tokenKey, value: token)
            KeychainService.save(key: KeychainService.tokenKey(for: payload.sub), value: token)
            UserDefaults.standard.set(payload.sub, forKey: Keys.username)
            UserDefaults.standard.set(payload.role, forKey: Keys.role)

            await APIClient.shared.setToken(token)

            // 保存账号
            await saveAccount(username: payload.sub)

            isLoading = false
            return true
        } catch {
            self.error = error.localizedDescription
            isLoading = false
            return false
        }
    }

    // MARK: - 快速登录

    func quickLogin(username: String) async -> Bool {
        guard let savedToken = KeychainService.load(key: KeychainService.tokenKey(for: username)) else {
            error = "未找到保存的凭证"
            return false
        }

        guard let payload = JWTPayload.decode(from: savedToken), !payload.isExpired else {
            error = "登录已过期，请重新输入密码"
            await removeSavedAccount(username: username)
            return false
        }

        isLoading = true
        token = savedToken
        self.username = payload.sub
        self.userRole = payload.role
        self.isAuthenticated = true

        KeychainService.save(key: KeychainService.tokenKey, value: savedToken)
        UserDefaults.standard.set(payload.sub, forKey: Keys.username)
        UserDefaults.standard.set(payload.role, forKey: Keys.role)

        await APIClient.shared.setToken(savedToken)
        await saveAccount(username: payload.sub)

        isLoading = false
        return true
    }

    // MARK: - 登出

    func logout() {
        wsManager.disconnect()
        token = nil
        isAuthenticated = false
        serverSelected = false
        serverId = ""
        chatMessages = []
        serverStatus = nil
        isBackendOnline = false

        KeychainService.delete(key: KeychainService.tokenKey)
        UserDefaults.standard.removeObject(forKey: Keys.serverId)
    }

    // MARK: - 多账号管理

    func loadSavedAccounts() async {
        guard let data = UserDefaults.standard.data(forKey: Keys.savedAccounts),
              let accounts = try? JSONDecoder().decode([SavedAccount].self, from: data) else {
            savedAccounts = []
            return
        }
        savedAccounts = accounts.sorted { $0.lastUsed > $1.lastUsed }
    }

    private func saveAccount(username: String) async {
        var accounts = savedAccounts.filter { $0.username != username }
        accounts.insert(SavedAccount(username: username, lastUsed: Date().timeIntervalSince1970 * 1000), at: 0)

        savedAccounts = accounts
        if let data = try? JSONEncoder().encode(accounts) {
            UserDefaults.standard.set(data, forKey: Keys.savedAccounts)
        }
    }

    func removeSavedAccount(username: String) async {
        savedAccounts.removeAll { $0.username == username }
        KeychainService.delete(key: KeychainService.tokenKey(for: username))

        if let data = try? JSONEncoder().encode(savedAccounts) {
            UserDefaults.standard.set(data, forKey: Keys.savedAccounts)
        }
    }

    // MARK: - 服务器选择

    func selectServer(_ id: String) {
        serverId = id
        serverSelected = true
        chatMessages = []
        serverStatus = nil
        isBackendOnline = false

        UserDefaults.standard.set(id, forKey: Keys.serverId)

        // 连接WebSocket
        if let token {
            wsManager.connect(token: token, serverId: id)
        }

        // 检测后端是否在线
        Task { await fetchServerStatus() }
    }

    func clearServerSelection() {
        wsManager.disconnect()
        serverSelected = false
        serverId = ""
        chatMessages = []
        serverStatus = nil
        isBackendOnline = false
        UserDefaults.standard.removeObject(forKey: Keys.serverId)
    }

    // MARK: - 服务器列表

    func fetchMyServers() async {
        do {
            let response = try await APIClient.shared.fetchMyServers()
            myServers = response.servers
        } catch {
            self.error = error.localizedDescription
        }
    }

    func fetchUnboundServers() async {
        do {
            let response = try await APIClient.shared.fetchUnboundServers()
            unboundServers = response.servers
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - 聊天

    func startChat(_ content: String) {
        // 先等待前一个任务取消完成，再启动新任务
        let previousTask = currentChatTask
        currentChatTask = nil
        previousTask?.cancel()
        let newTask = Task {
            // 确保前一个任务已完成
            _ = await previousTask?.value
            guard !Task.isCancelled else { return }
            await sendMessage(content)
        }
        currentChatTask = newTask
    }

    func cancelChat() {
        currentChatTask?.cancel()
        currentChatTask = nil
        isLoading = false
    }

    func sendMessage(_ content: String) async {
        guard !content.isEmpty, !serverId.isEmpty else { return }

        let userMsg = ChatMessage.user(content)
        chatMessages.append(userMsg)

        // 限制100条
        if chatMessages.count > 100 {
            chatMessages = Array(chatMessages.suffix(100))
        }

        isLoading = true

        do {
            let response = try await APIClient.shared.sendChat(
                message: content,
                serverId: serverId,
                queryOnly: queryOnlyMode,
                modelTier: modelTier?.rawValue
            )

            guard !Task.isCancelled else { return }

            var text = response.message.trimmingCharacters(in: .whitespacesAndNewlines)
            if text.isEmpty && response.review == nil {
                text = "（AI 未返回描述，请重试或换个问法）"
            }
            if response.degraded == true, let warn = response.degraded_message, !warn.isEmpty {
                text = "⚠️ \(warn)\n\n\(text)"
            }
            if !text.isEmpty || response.review != nil {
                let assistantMsg = ChatMessage.assistant(text, review: response.review)
                chatMessages.append(assistantMsg)
            }
        } catch is CancellationError {
            // 用户取消，不显示错误
        } catch let error as URLError where error.code == .cancelled {
            // URL请求被取消
        } catch {
            if !Task.isCancelled {
                let errorMsg = ChatMessage.assistant("请求失败: \(error.localizedDescription)")
                chatMessages.append(errorMsg)
            }
        }

        isLoading = false
        currentChatTask = nil
    }

    func confirmCommand(pendingId: String, action: String) async {
        do {
            let response = try await APIClient.shared.confirmCommand(pendingId: pendingId, action: action)
            let msg = ChatMessage.assistant(response.message)
            chatMessages.append(msg)

            // 清除对应的pending审核
            if let index = chatMessages.lastIndex(where: { $0.review?.pending_id == pendingId }) {
                chatMessages[index].review = nil
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - 设置

    func toggleQueryOnlyMode() {
        queryOnlyMode.toggle()
        UserDefaults.standard.set(queryOnlyMode, forKey: Keys.queryOnly)
    }

    func setModelTier(_ tier: ModelTier?) {
        modelTier = tier
        if let tier {
            UserDefaults.standard.set(tier.rawValue, forKey: Keys.modelTier)
        } else {
            UserDefaults.standard.removeObject(forKey: Keys.modelTier)
        }
    }

    // MARK: - 后端状态检测

    func fetchServerStatus() async {
        guard !serverId.isEmpty else { return }
        do {
            serverStatus = try await APIClient.shared.fetchStatus(serverId: serverId)
            isBackendOnline = true
        } catch {
            isBackendOnline = false
        }
    }

    // MARK: - WebSocket回调

    private func setupWSCallbacks() {
        wsManager.onStatusUpdate = { [weak self] status in
            self?.serverStatus = status
        }

        wsManager.onChatResponse = { [weak self] message in
            let msg = ChatMessage.assistant(message)
            self?.chatMessages.append(msg)
        }
    }
}
