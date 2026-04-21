import SwiftUI

struct ContentView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Group {
            if !appState.isAuthenticated {
                LoginView()
            } else if !appState.serverSelected {
                ServerSelectView()
            } else {
                MainTabView()
            }
        }
        .task {
            await appState.restoreSession()
        }
    }
}
