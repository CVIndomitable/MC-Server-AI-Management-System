import Foundation

// MARK: - API客户端

actor APIClient {
    static let shared = APIClient()

    private let baseURL = "http://47.113.221.26/mc-admin-dev"
    private let session: URLSession

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        self.session = URLSession(configuration: config)
    }

    /// 每次请求都从 Keychain 读取当前 token，避免账号切换后 APIClient 仍持有旧 token
    /// Keychain 在 tokenKey 下存的是"当前活跃账号"的 token，登出时会被删除
    private func currentToken() -> String? {
        KeychainService.load(key: KeychainService.tokenKey)
    }

    /// 兼容旧调用点的空操作；真正的 token 始终从 Keychain 读取
    func setToken(_ token: String?) {}

    // MARK: - 通用请求

    private func request<T: Decodable>(
        _ method: String,
        path: String,
        body: (any Encodable)? = nil,
        query: [String: String]? = nil
    ) async throws -> T {
        var urlString = "\(baseURL)\(path)"

        if let query, !query.isEmpty {
            guard var components = URLComponents(string: urlString) else {
                throw APIError.invalidResponse
            }
            components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
            guard let resolvedURL = components.url else {
                throw APIError.invalidResponse
            }
            urlString = resolvedURL.absoluteString
        }

        guard let url = URL(string: urlString) else {
            throw APIError.invalidResponse
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let token = currentToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        if let body {
            request.httpBody = try JSONEncoder().encode(body)
        }

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200..<300:
            do {
                return try JSONDecoder().decode(T.self, from: data)
            } catch let decodingError as DecodingError {
                throw APIError.server("数据解析失败: \(decodingError.localizedDescription)")
            }
        case 401:
            throw APIError.unauthorized
        case 403:
            throw APIError.forbidden
        case 404:
            throw APIError.notFound
        case 422:
            if let detail = try? JSONDecoder().decode(ValidationError.self, from: data) {
                throw APIError.validation(detail.detail)
            }
            throw APIError.validation("请求参数错误")
        default:
            if let msg = try? JSONDecoder().decode(MessageResponse.self, from: data) {
                throw APIError.server(msg.message)
            }
            throw APIError.server("服务器错误 (\(httpResponse.statusCode))")
        }
    }

    // MARK: - Auth API

    func login(username: String, password: String) async throws -> LoginResponse {
        try await request("POST", path: "/api/v1/auth/login",
                          body: LoginRequest(username: username, password: password))
    }

    func register(username: String, password: String, role: String) async throws -> UserInfo {
        try await request("POST", path: "/api/v1/auth/register",
                          body: RegisterRequest(username: username, password: password, role: role))
    }

    func changePassword(oldPassword: String, newPassword: String) async throws -> MessageResponse {
        try await request("PUT", path: "/api/v1/auth/password",
                          body: ChangePasswordRequest(old_password: oldPassword, new_password: newPassword))
    }

    func resetPassword(username: String, newPassword: String) async throws -> MessageResponse {
        try await request("PUT", path: "/api/v1/auth/users/\(username)/password",
                          body: ResetPasswordRequest(new_password: newPassword))
    }

    func listUsers() async throws -> UsersResponse {
        try await request("GET", path: "/api/v1/auth/users")
    }

    func deleteUser(username: String) async throws -> MessageResponse {
        try await request("DELETE", path: "/api/v1/auth/users/\(username)")
    }

    // MARK: - Chat API

    func sendChat(message: String, serverId: String, queryOnly: Bool = false, modelTier: String? = nil) async throws -> ChatResponse {
        try await request("POST", path: "/api/v1/chat",
                          body: ChatRequest(message: message, server_id: serverId,
                                            query_only: queryOnly, model_tier: modelTier))
    }

    func confirmCommand(pendingId: String, action: String) async throws -> ConfirmResponse {
        try await request("POST", path: "/api/v1/chat/confirm/\(pendingId)",
                          query: ["action": action])
    }

    // MARK: - Server API

    func fetchMyServers() async throws -> MyServersResponse {
        try await request("GET", path: "/api/v1/servers/my")
    }

    func fetchUnboundServers() async throws -> UnboundServersResponse {
        try await request("GET", path: "/api/v1/servers/unbound")
    }

    func bindServer(serverId: String) async throws -> BindResponse {
        try await request("POST", path: "/api/v1/servers/\(serverId)/bind")
    }

    func fetchBindRequests(serverId: String) async throws -> BindRequestsResponse {
        try await request("GET", path: "/api/v1/servers/\(serverId)/requests")
    }

    func approveRequest(serverId: String, requestId: Int) async throws -> MessageResponse {
        try await request("POST", path: "/api/v1/servers/\(serverId)/requests/\(requestId)/approve")
    }

    func rejectRequest(serverId: String, requestId: Int) async throws -> MessageResponse {
        try await request("POST", path: "/api/v1/servers/\(serverId)/requests/\(requestId)/reject")
    }

    func fetchServerUsers(serverId: String) async throws -> ServerUsersResponse {
        try await request("GET", path: "/api/v1/servers/\(serverId)/users")
    }

    func updateServerName(serverId: String, name: String) async throws -> MessageResponse {
        try await request("PUT", path: "/api/v1/servers/\(serverId)/name",
                          body: UpdateNameRequest(name: name))
    }

    func unbindUser(serverId: String, username: String) async throws -> MessageResponse {
        try await request("DELETE", path: "/api/v1/servers/\(serverId)/unbind/\(username)")
    }

    // MARK: - Status API

    func fetchStatus(serverId: String) async throws -> ServerStatus {
        try await request("GET", path: "/api/v1/status/\(serverId)")
    }

    // MARK: - Memory API

    func fetchGlobalMemory() async throws -> MemoryResponse {
        try await request("GET", path: "/api/v1/memory/global")
    }

    func updateGlobalMemory(content: String) async throws -> MessageResponse {
        try await request("PUT", path: "/api/v1/memory/global",
                          body: MemoryUpdateRequest(content: content, entries: nil))
    }

    func fetchAdminMemory(adminId: String) async throws -> MemoryResponse {
        try await request("GET", path: "/api/v1/memory/admin/\(adminId)")
    }

    func updateAdminMemory(adminId: String, content: String) async throws -> MessageResponse {
        try await request("PUT", path: "/api/v1/memory/admin/\(adminId)",
                          body: MemoryUpdateRequest(content: content, entries: nil))
    }

    func fetchServerMemory(serverId: String) async throws -> MemoryResponse {
        try await request("GET", path: "/api/v1/memory/server/\(serverId)")
    }

    func updateServerMemory(serverId: String, content: String) async throws -> MessageResponse {
        try await request("PUT", path: "/api/v1/memory/server/\(serverId)",
                          body: MemoryUpdateRequest(content: content, entries: nil))
    }

    // MARK: - Health

    func healthCheck() async throws -> HealthResponse {
        try await request("GET", path: "/api/v1/health")
    }

    // MARK: - 档案馆（Spark profiler 采样）

    func listSparkArchives(serverId: String, limit: Int = 20, offset: Int = 0) async throws -> SparkProfileListResponse {
        try await request(
            "GET", path: "/api/v1/archive/spark/\(serverId)",
            query: ["limit": String(limit), "offset": String(offset)]
        )
    }

    func getSparkArchive(serverId: String, profileId: Int) async throws -> SparkProfileDetail {
        try await request("GET", path: "/api/v1/archive/spark/\(serverId)/\(profileId)")
    }

    /// 触发 AI 分析（启用扩展思考）。耗时较长，调用方应显示 loading。
    func analyzeSparkArchive(serverId: String, profileId: Int) async throws -> AnalyzeArchiveResponse {
        // 分析需要较长时间（扩展思考），绕过默认 30s 超时
        let urlString = "\(baseURL)/api/v1/archive/spark/\(serverId)/\(profileId)/analyze"
        guard let url = URL(string: urlString) else { throw APIError.invalidResponse }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = currentToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        // 分析最多 3 分钟
        req.timeoutInterval = 180
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 180
        config.timeoutIntervalForResource = 180
        let longSession = URLSession(configuration: config)
        let (data, response) = try await longSession.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        switch http.statusCode {
        case 200..<300:
            return try JSONDecoder().decode(AnalyzeArchiveResponse.self, from: data)
        case 401: throw APIError.unauthorized
        case 403: throw APIError.forbidden
        case 404: throw APIError.notFound
        default:
            if let msg = try? JSONDecoder().decode(ValidationError.self, from: data) {
                throw APIError.server(msg.detail)
            }
            throw APIError.server("分析失败 (\(http.statusCode))")
        }
    }

    func deleteSparkArchive(serverId: String, profileId: Int) async throws -> MessageResponse {
        try await request("DELETE", path: "/api/v1/archive/spark/\(serverId)/\(profileId)")
    }

    // MARK: - Provider 管理（仅管理员）

    func listProviders() async throws -> ProvidersResponse {
        try await request("GET", path: "/api/v1/admin/providers")
    }

    func createProvider(_ req: ProviderCreateRequest) async throws -> ApiProvider {
        try await request("POST", path: "/api/v1/admin/providers", body: req)
    }

    func updateProvider(id: Int, req: ProviderUpdateRequest) async throws -> ApiProvider {
        try await request("PUT", path: "/api/v1/admin/providers/\(id)", body: req)
    }

    func deleteProvider(id: Int) async throws -> MessageResponse {
        try await request("DELETE", path: "/api/v1/admin/providers/\(id)")
    }
}

// MARK: - 错误类型

enum APIError: LocalizedError {
    case invalidResponse
    case unauthorized
    case forbidden
    case notFound
    case validation(String)
    case server(String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "无效响应"
        case .unauthorized: return "登录已过期，请重新登录"
        case .forbidden: return "没有权限执行此操作"
        case .notFound: return "资源不存在"
        case .validation(let msg): return msg
        case .server(let msg): return msg
        }
    }
}

struct ValidationError: Codable {
    let detail: String
}

// 兼容detail为数组的情况
extension ValidationError {
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if let str = try? container.decode(String.self, forKey: .detail) {
            self.detail = str
        } else {
            self.detail = "请求参数错误"
        }
    }

    enum CodingKeys: String, CodingKey {
        case detail
    }
}
