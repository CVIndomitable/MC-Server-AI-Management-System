import Foundation

// MARK: - 记忆系统

struct MemoryEntry: Codable, Identifiable {
    var id: String?
    var tags: [String]
    var content: String
    var pinned: Bool

    init(id: String? = nil, tags: [String] = [], content: String = "", pinned: Bool = false) {
        self.id = id
        self.tags = tags
        self.content = content
        self.pinned = pinned
    }
}

struct MemoryResponse: Codable {
    let content: String
    let entries: [MemoryEntry]?
    let updated_at: String?
}

struct MemoryUpdateRequest: Codable {
    let content: String
    let entries: [MemoryEntry]?
}

struct MemoryBackup: Codable, Identifiable {
    var id: Int { version }
    let version: Int
    let timestamp: String
    let content_preview: String
}

struct MemoryBackupsResponse: Codable {
    let backups: [MemoryBackup]
}

struct MemoryRollbackRequest: Codable {
    let version: Int
}
