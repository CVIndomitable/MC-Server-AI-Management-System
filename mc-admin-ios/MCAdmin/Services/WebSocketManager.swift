import Foundation

// MARK: - WebSocket管理器

@Observable
final class WebSocketManager {
    var isConnected = false

    private var webSocket: URLSessionWebSocketTask?
    private let wsURL = "ws://47.113.221.26/mc-admin/ws"
    private var token: String?
    private var serverId: String?
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 10
    private let reconnectInterval: TimeInterval = 5
    private var reconnectTask: Task<Void, Never>?
    private var authTimeoutTask: Task<Void, Never>?
    private var isAuthenticated = false
    private var intentionalDisconnect = false

    var onStatusUpdate: ((ServerStatus) -> Void)?
    var onChatResponse: ((String) -> Void)?
    var onConnectionChange: ((Bool) -> Void)?

    func connect(token: String, serverId: String) {
        self.token = token
        self.serverId = serverId
        self.intentionalDisconnect = false
        self.reconnectAttempts = 0
        doConnect()
    }

    func disconnect() {
        intentionalDisconnect = true
        reconnectTask?.cancel()
        reconnectTask = nil
        authTimeoutTask?.cancel()
        authTimeoutTask = nil
        webSocket?.cancel(with: .goingAway, reason: nil)
        webSocket = nil
        setConnected(false)
        isAuthenticated = false
    }

    // MARK: - 内部连接

    private func doConnect() {
        guard let url = URL(string: wsURL) else { return }

        let session = URLSession(configuration: .default)
        webSocket = session.webSocketTask(with: url)
        webSocket?.resume()

        sendAuth()
        startAuthTimeout()
        receiveMessage()
    }

    private func sendAuth() {
        guard let token, let serverId else { return }

        let auth: [String: String] = [
            "type": "auth",
            "token": token,
            "server_id": serverId,
        ]

        guard let data = try? JSONSerialization.data(withJSONObject: auth),
              let text = String(data: data, encoding: .utf8) else { return }

        webSocket?.send(.string(text)) { _ in }
    }

    private func startAuthTimeout() {
        authTimeoutTask?.cancel()
        authTimeoutTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(5))
            guard let self, !Task.isCancelled, !self.isAuthenticated else { return }
            // 认证超时，断开重连
            self.webSocket?.cancel(with: .goingAway, reason: nil)
            self.scheduleReconnect()
        }
    }

    private func receiveMessage() {
        webSocket?.receive { [weak self] result in
            guard let self else { return }

            switch result {
            case .success(let message):
                switch message {
                case .string(let text):
                    self.handleMessage(text)
                default:
                    break
                }
                self.receiveMessage()

            case .failure:
                if !self.intentionalDisconnect {
                    self.setConnected(false)
                    self.scheduleReconnect()
                }
            }
        }
    }

    private func handleMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else { return }

        // 过滤非当前服务器的消息
        if let msgServerId = json["server_id"] as? String, msgServerId != serverId {
            return
        }

        switch type {
        case "auth_success", "auth_response":
            isAuthenticated = true
            authTimeoutTask?.cancel()
            reconnectAttempts = 0
            setConnected(true)

        case "auth_failed":
            disconnect()

        case "status":
            if let statusData = json["data"] as? [String: Any] {
                parseStatus(json: statusData, serverId: json["server_id"] as? String ?? serverId ?? "")
            }

        case "chat_response":
            if let msg = json["message"] as? String {
                Task { @MainActor in
                    self.onChatResponse?(msg)
                }
            }

        default:
            break
        }
    }

    private func parseStatus(json: [String: Any], serverId: String) {
        let status = ServerStatus(
            server_id: serverId,
            tps: json["tps"] as? Double ?? 0,
            players: json["players"] as? [String] ?? [],
            memory_used_mb: json["memory_used_mb"] as? Int ?? 0,
            memory_max_mb: json["memory_max_mb"] as? Int ?? 0,
            recent_errors: json["recent_errors"] as? [String] ?? [],
            timestamp: json["timestamp"] as? TimeInterval,
            online: true,
            last_update: nil
        )

        Task { @MainActor in
            self.onStatusUpdate?(status)
        }
    }

    private func setConnected(_ connected: Bool) {
        Task { @MainActor in
            self.isConnected = connected
            self.onConnectionChange?(connected)
        }
    }

    // MARK: - 重连

    private func scheduleReconnect() {
        guard !intentionalDisconnect, reconnectAttempts < maxReconnectAttempts else { return }

        reconnectAttempts += 1
        let delay = reconnectInterval * Double(min(reconnectAttempts, 5))

        reconnectTask?.cancel()
        reconnectTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(delay))
            guard let self, !Task.isCancelled, !self.intentionalDisconnect else { return }
            self.doConnect()
        }
    }
}
