import Foundation

// MARK: - 档案馆（Spark profiler 采样档案）

struct SparkProfileSummary: Codable, Identifiable, Hashable {
    let id: Int
    let admin_id: String
    let server_id: String
    let started_at: String
    let stopped_at: String?
    let start_command: String?
    let profile_url: String?
    let ai_model: String?
    let ai_provider: String?
    let analyzed_at: String?
    let status: String
    let error: String?
}

struct SparkProfileDetail: Codable, Identifiable, Hashable {
    let id: Int
    let admin_id: String
    let server_id: String
    let started_at: String
    let stopped_at: String?
    let start_command: String?
    let profile_url: String?
    let ai_model: String?
    let ai_provider: String?
    let analyzed_at: String?
    let status: String
    let error: String?
    let stop_output: String?
    let profile_raw: String?
    let ai_analysis: String?
    let ai_thinking: String?
}

struct SparkProfileListResponse: Codable {
    let items: [SparkProfileSummary]
    let total: Int
    let limit: Int
    let offset: Int
}

struct AnalyzeArchiveResponse: Codable {
    let ok: Bool
    let profile: SparkProfileDetail
}

// 状态常量（与后端一致）
enum SparkProfileStatus {
    static let running = "running"
    static let stopped = "stopped"
    static let analyzing = "analyzing"
    static let analyzed = "analyzed"
    static let failed = "failed"
}
