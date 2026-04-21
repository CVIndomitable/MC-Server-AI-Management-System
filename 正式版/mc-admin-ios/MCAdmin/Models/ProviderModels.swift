import Foundation

struct ApiProvider: Codable, Identifiable {
    let id: Int
    let name: String
    let base_url: String
    let api_key_tail: String
    let priority: Int
    let enabled: Bool
    let model_map: [String: String]?
    let created_at: String
    let updated_at: String
}

struct ProvidersResponse: Codable {
    let providers: [ApiProvider]
}

struct ProviderCreateRequest: Codable {
    let name: String
    let base_url: String
    let api_key: String
    let priority: Int
    let enabled: Bool
    let model_map: [String: String]?
}

struct ProviderUpdateRequest: Codable {
    let name: String?
    let base_url: String?
    let api_key: String?
    let priority: Int?
    let enabled: Bool?
    let model_map: [String: String]?
    let clear_model_map: Bool
}
