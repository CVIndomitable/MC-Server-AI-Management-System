import Foundation

// MARK: - 聊天消息

struct ChatMessage: Identifiable {
    let id: String
    let role: String // "user" | "assistant"
    var content: String  // 流式更新用 var
    let timestamp: TimeInterval
    var review: ReviewInfo?

    var isUser: Bool { role == "user" }

    static func user(_ content: String) -> ChatMessage {
        ChatMessage(
            id: UUID().uuidString,
            role: "user",
            content: content,
            timestamp: Date().timeIntervalSince1970 * 1000
        )
    }

    static func assistant(_ content: String, review: ReviewInfo? = nil) -> ChatMessage {
        ChatMessage(
            id: UUID().uuidString,
            role: "assistant",
            content: content,
            timestamp: Date().timeIntervalSince1970 * 1000,
            review: review
        )
    }
}

// MARK: - 审核信息

struct ReviewInfo: Codable {
    let status: String // "approved" | "rejected" | "pending_confirmation"
    let risk_level: String? // "low" | "medium" | "high"
    let reviewed_by: String?
    let reason: String?
    let suggestion: String?
    let pending_id: String?
    let command: String?
    let expires_in: Int?

    var isPending: Bool { status == "pending_confirmation" }
}

// MARK: - 聊天请求/响应

struct ChatRequest: Codable {
    let message: String
    let server_id: String
    let query_only: Bool?
    let model_tier: String?
}

struct ChatResponse: Codable {
    let message: String
    let command_executed: AnyCodable?
    let review: ReviewInfo?
    let timestamp: String
    let degraded: Bool?
    let degraded_message: String?
}

// MARK: - 确认请求

struct ConfirmResponse: Codable {
    let success: Bool
    let message: String
    let output: String?
    let command: String?
}

// MARK: - 工具执行状态

struct ToolExecutingStatus {
    let id: String
    let tool: String
    let label: String
    let startedAt: Date
}

// MARK: - 模型等级

enum ModelTier: String, CaseIterable {
    case flash
    case standard
    case pro

    var displayName: String {
        switch self {
        case .flash: return "快速"
        case .standard: return "标准"
        case .pro: return "专业"
        }
    }
}

// MARK: - AnyCodable辅助

struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else if let string = try? container.decode(String.self) {
            value = string
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else {
            value = NSNull()
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let dict = value as? [String: Any] {
            try container.encode(dict.mapValues { AnyCodable($0) })
        } else if let array = value as? [Any] {
            try container.encode(array.map { AnyCodable($0) })
        } else if let string = value as? String {
            try container.encode(string)
        } else if let int = value as? Int {
            try container.encode(int)
        } else if let double = value as? Double {
            try container.encode(double)
        } else if let bool = value as? Bool {
            try container.encode(bool)
        } else {
            try container.encodeNil()
        }
    }
}
