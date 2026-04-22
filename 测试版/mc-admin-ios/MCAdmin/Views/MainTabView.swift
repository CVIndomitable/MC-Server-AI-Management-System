import SwiftUI

struct MainTabView: View {
    @Environment(AppState.self) private var appState
    @AppStorage("actionsTabEnabled") private var actionsTabEnabled = false

    var body: some View {
        TabView {
            ChatView()
                .tabItem {
                    Label("聊天", systemImage: "bubble.left.and.bubble.right")
                }

            StatusView()
                .tabItem {
                    Label("状态", systemImage: "chart.bar")
                }

            ArchiveView()
                .tabItem {
                    Label("档案馆", systemImage: "archivebox")
                }

            if actionsTabEnabled {
                ActionsView()
                    .tabItem {
                        Label("操作", systemImage: "bolt.fill")
                    }
            }

            SettingsView()
                .tabItem {
                    Label("设置", systemImage: "gearshape")
                }
        }
        .tint(Theme.primary)
    }
}
