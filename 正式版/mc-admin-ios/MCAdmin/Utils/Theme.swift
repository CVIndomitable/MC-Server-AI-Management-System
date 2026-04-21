import SwiftUI

// MARK: - 暗色主题

enum Theme {
    // 背景
    static let background = Color(hex: 0x1A1A1A)
    static let cardBackground = Color(hex: 0x2A2A2A)
    static let border = Color(hex: 0x333333)

    // 强调色
    static let primary = Color(hex: 0x007AFF)
    static let orange = Color(hex: 0xFF9800)
    static let red = Color(hex: 0xF44336)
    static let green = Color(hex: 0x4CAF50)
    static let cyan = Color(hex: 0x00BCD4)
    static let purple = Color(hex: 0x9C27B0)

    // 文字
    static let textPrimary = Color.white
    static let textSecondary = Color(hex: 0xCCCCCC)
    static let textMuted = Color(hex: 0x888888)
    static let textDisabled = Color(hex: 0x666666)

    // 状态
    static let online = Color(hex: 0x34C759)
    static let offline = Color(hex: 0x666666)

    // TPS颜色
    static func tpsColor(_ tps: Double) -> Color {
        if tps >= 19 { return green }
        if tps >= 15 { return orange }
        return red
    }
}

extension Color {
    init(hex: UInt, alpha: Double = 1.0) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: alpha
        )
    }
}
