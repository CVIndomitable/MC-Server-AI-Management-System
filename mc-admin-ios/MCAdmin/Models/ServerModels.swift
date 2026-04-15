import Foundation

// MARK: - 服务器信息

struct UserServerInfo: Codable, Identifiable {
    var id: String { server_id }
    let server_id: String
    let name: String
    let role: String // "owner" | "admin"
    let online: Bool
    let bound_at: String
}

struct ServerInfo: Codable, Identifiable {
    var id: String { server_id }
    let server_id: String
    let name: String
    let online: Bool
    let created_at: String
    let last_seen_at: String?
}

struct MyServersResponse: Codable {
    let servers: [UserServerInfo]
}

struct UnboundServersResponse: Codable {
    let servers: [ServerInfo]
}

// MARK: - 绑定请求

struct BindRequest: Codable, Identifiable {
    let id: Int
    let username: String
    let server_id: String
    let status: String // "pending" | "approved" | "rejected"
    let created_at: String
    let resolved_at: String?
    let resolved_by: String?
}

struct BindRequestsResponse: Codable {
    let requests: [BindRequest]
}

// MARK: - 绑定结果

struct BindResponse: Codable {
    let server_id: String?
    let name: String?
    let role: String?
    let online: Bool?
    let bound_at: String?
    let message: String?
}

// MARK: - 服务器用户

struct ServerUser: Codable, Identifiable {
    var id: String { username }
    let username: String
    let role: String
    let bound_at: String
}

struct ServerUsersResponse: Codable {
    let users: [ServerUser]
}

// MARK: - 服务器状态

struct ServerStatus: Codable {
    let server_id: String
    let tps: Double
    let players: [String]
    let memory_used_mb: Int
    let memory_max_mb: Int
    let recent_errors: [String]
    let timestamp: TimeInterval?
    let online: Bool?
    let last_update: String?
}

// MARK: - 服务器名称更新

struct UpdateNameRequest: Codable {
    let name: String
}

// MARK: - 健康检查

struct HealthResponse: Codable {
    let status: String
    let checks: HealthChecks?
}

struct HealthChecks: Codable {
    let api: String?
    let redis: String?
    let database: String?
}
