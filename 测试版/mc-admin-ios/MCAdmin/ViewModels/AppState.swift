import Foundation
import SwiftUI

// MARK: - 全局状态管理

@MainActor
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
    var isThinking = false       // AI 正在思考/生成文本
    var isExecutingTool = false  // 正在执行工具
    var currentTool: ToolExecutingStatus?  // 当前执行的工具
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
            let tokenSaved = KeychainService.save(key: KeychainService.tokenKey, value: token)
            let accountTokenSaved = KeychainService.save(key: KeychainService.tokenKey(for: payload.sub), value: token)

            if !tokenSaved || !accountTokenSaved {
                print("⚠️ Failed to save credentials to Keychain")
            }

            UserDefaults.standard.set(payload.sub, forKey: Keys.username)
            UserDefaults.standard.set(payload.role, forKey: Keys.role)

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
        isThinking = false
        isExecutingTool = false
        currentTool = nil
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
        isThinking = true

        // 创建占位 assistant 消息，流式更新其 content
        let assistantId = UUID().uuidString
        let placeholder = ChatMessage(id: assistantId, role: "assistant", content: "", timestamp: Date().timeIntervalSince1970 * 1000)
        chatMessages.append(placeholder)

        do {
            var components = URLComponents(string: "\(APIClient.shared.baseURL)/api/v1/chat/stream")
            components?.queryItems = [
                URLQueryItem(name: "message", value: content),
                URLQueryItem(name: "server_id", value: serverId),
                URLQueryItem(name: "query_only", value: queryOnlyMode ? "true" : "false"),
            ]
            if let tier = modelTier?.rawValue {
                components?.queryItems?.append(URLQueryItem(name: "model_tier", value: tier))
            }

            guard let url = components?.url else {
                // 回退到 REST API
                await _sendMessageRest(content, assistantId: assistantId)
                return
            }

            var request = URLRequest(url: url)
            request.timeoutInterval = 60
            if let token = KeychainService.load(key: KeychainService.tokenKey) {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }

            let (bytes, response) = try await URLSession.shared.bytes(for: request)

            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                // 非 200 回退 REST
                await _sendMessageRest(content, assistantId: assistantId)
                return
            }

            var currentText = ""
            var currentEvent = ""
            var currentData = ""

            for try await line in bytes.lines {
                guard !Task.isCancelled else { break }

                if line.hasPrefix("event: ") {
                    currentEvent = String(line.dropFirst(7))
                } else if line.hasPrefix("data: ") {
                    currentData = String(line.dropFirst(6))
                } else if line.isEmpty, !currentEvent.isEmpty,
                          let data = currentData.data(using: .utf8),
                          let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {

                    switch currentEvent {
                    case "text_delta":
                        if let text = json["text"] as? String {
                            currentText += text
                            _updateMessage(id: assistantId, text: currentText)
                        }
                        if isThinking {
                            isThinking = false
                        }
                    case "tool_start":
                        isExecutingTool = true
                        isThinking = false
                        currentTool = ToolExecutingStatus(
                            id: json["id"] as? String ?? "",
                            tool: json["tool"] as? String ?? "",
                            label: json["label"] as? String ?? "",
                            startedAt: Date()
                        )
                    case "tool_end":
                        isExecutingTool = false
                        currentTool = nil
                        // 工具执行完，AI 将开始总结，恢复思考中状态
                        isThinking = true
                    case "done":
                        _updateMessage(id: assistantId, text: currentText)
                        isThinking = false
                        isExecutingTool = false
                        currentTool = nil
                    case "error":
                        let errText = json["error"] as? String ?? "未知错误"
                        _updateMessage(id: assistantId, text: "AI处理失败: \(errText)")
                        isThinking = false
                        isExecutingTool = false
                        currentTool = nil
                    default:
                        break
                    }
                    currentEvent = ""
                    currentData = ""
                }
            }

            // 如果流结束但没收到任何文本，回退 REST
            if currentText.isEmpty {
                await _sendMessageRest(content, assistantId: assistantId)
            }
        } catch is CancellationError {
            removeMessage(id: assistantId)
        } catch let error as URLError where error.code == .cancelled {
            removeMessage(id: assistantId)
        } catch {
            if !Task.isCancelled {
                // 流式失败，回退到 REST
                removeMessage(id: assistantId)
                await _sendMessageRest(content, assistantId: assistantId)
            }
        }

        isLoading = false
        currentChatTask = nil
    }

    /// REST 回退：旧版一次性请求
    private func _sendMessageRest(_ content: String, assistantId: String) async {
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
            _updateMessage(id: assistantId, text: text, review: response.review)
        } catch is CancellationError {
            removeMessage(id: assistantId)
        } catch let error as URLError where error.code == .cancelled {
            removeMessage(id: assistantId)
        } catch {
            if !Task.isCancelled {
                _updateMessage(id: assistantId, text: "请求失败: \(error.localizedDescription)")
            }
        }
    }

    /// 更新指定ID的 assistant 消息
    private func _updateMessage(id: String, text: String, review: ReviewInfo? = nil) {
        guard let index = chatMessages.lastIndex(where: { $0.id == id }) else { return }
        chatMessages[index].content = text
        if let review {
            chatMessages[index].review = review
        }
    }

    private func removeMessage(id: String) {
        chatMessages.removeAll(where: { $0.id == id })
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

    // MARK: - 新对话

    func clearConversation() async {
        cancelChat()
        chatMessages = []

        guard !serverId.isEmpty else { return }

        do {
            _ = try await APIClient.shared.clearConversation(serverId: serverId)
        } catch {
            // 后端清除失败不影响本地清空
            print("清除对话历史失败: \(error.localizedDescription)")
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
            guard let self else { return }
            self.serverStatus = status
        }

        wsManager.onChatResponse = { [weak self] message in
            guard let self else { return }
            let msg = ChatMessage.assistant(message)
            self.chatMessages.append(msg)

            if self.chatMessages.count > 100 {
                self.chatMessages = Array(self.chatMessages.suffix(100))
            }
        }
    }
}
