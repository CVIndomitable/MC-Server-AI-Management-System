import Foundation

// MARK: - 请求

struct LoginRequest: Codable {
    let username: String
    let password: String
}

struct RegisterRequest: Codable {
    let username: String
    let password: String
    let role: String // "admin" | "user"
}

struct ChangePasswordRequest: Codable {
    let old_password: String
    let new_password: String
}

struct ResetPasswordRequest: Codable {
    let new_password: String
}

// MARK: - 响应

struct LoginResponse: Codable {
    let access_token: String
    let token_type: String
}

struct UserInfo: Codable, Identifiable {
    var id: String { username }
    let username: String
    let role: String
    let created_at: String
}

struct UsersResponse: Codable {
    let users: [UserInfo]
}

struct MessageResponse: Codable {
    let message: String
}

// MARK: - JWT解码

struct JWTPayload {
    let sub: String
    let role: String
    let exp: TimeInterval

    var isExpired: Bool {
        Date().timeIntervalSince1970 > (exp - 60)
    }
}

extension JWTPayload {
    static func decode(from token: String) -> JWTPayload? {
        let parts = token.split(separator: ".")
        guard parts.count >= 2 else { return nil }

        var base64 = String(parts[1])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")

        while base64.count % 4 != 0 {
            base64.append("=")
        }

        guard let data = Data(base64Encoded: base64),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let sub = json["sub"] as? String,
              let role = json["role"] as? String,
              let exp = json["exp"] as? TimeInterval else {
            return nil
        }

        return JWTPayload(sub: sub, role: role, exp: exp)
    }
}

// MARK: - 本地保存的账号

struct SavedAccount: Codable, Identifiable {
    var id: String { username }
    let username: String
    let lastUsed: TimeInterval
}
