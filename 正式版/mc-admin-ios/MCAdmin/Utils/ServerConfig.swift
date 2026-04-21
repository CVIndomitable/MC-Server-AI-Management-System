import Foundation

/// 后端地址配置。优先级：UserDefaults 覆盖 > Info.plist 注入 > 编译期默认。
/// 切换部署环境时无需重新打包，用户可通过 Settings 界面改 UserDefaults。
enum ServerConfig {
    private static let baseURLKey = "MCAdminBaseURL"
    private static let fallbackBaseURL = "https://mc.example.com/mc-admin"

    /// HTTP(S) API 根，如 https://host/mc-admin
    static var baseURL: String {
        if let override = UserDefaults.standard.string(forKey: baseURLKey),
           !override.trimmingCharacters(in: .whitespaces).isEmpty {
            return normalize(override)
        }
        if let fromPlist = Bundle.main.object(forInfoDictionaryKey: baseURLKey) as? String,
           !fromPlist.trimmingCharacters(in: .whitespaces).isEmpty {
            return normalize(fromPlist)
        }
        return fallbackBaseURL
    }

    /// 对应的 WebSocket 根，自动把 http/https 前缀替换为 ws/wss
    static var webSocketURL: String {
        let base = baseURL
        if base.hasPrefix("https://") {
            return "wss://" + base.dropFirst("https://".count) + "/ws"
        }
        if base.hasPrefix("http://") {
            return "ws://" + base.dropFirst("http://".count) + "/ws"
        }
        // 未知协议：按 wss 处理，明文出站视为故障
        return "wss://" + base + "/ws"
    }

    static func overrideBaseURL(_ value: String?) {
        if let value, !value.trimmingCharacters(in: .whitespaces).isEmpty {
            UserDefaults.standard.set(value, forKey: baseURLKey)
        } else {
            UserDefaults.standard.removeObject(forKey: baseURLKey)
        }
    }

    private static func normalize(_ raw: String) -> String {
        var s = raw.trimmingCharacters(in: .whitespaces)
        while s.hasSuffix("/") { s.removeLast() }
        return s
    }
}
