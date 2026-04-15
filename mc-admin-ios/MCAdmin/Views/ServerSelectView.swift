import SwiftUI

struct ServerSelectView: View {
    @Environment(AppState.self) private var appState

    @State private var selectedTab = 0
    @State private var pendingRequests: [String: [BindRequest]] = [:]
    @State private var expandedServer: String?

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Tab切换
                    Picker("", selection: $selectedTab) {
                        Text("我的服务器").tag(0)
                        if appState.isAdmin {
                            Text("未绑定").tag(1)
                        }
                    }
                    .pickerStyle(.segmented)
                    .padding()

                    if selectedTab == 0 {
                        myServersList
                    } else {
                        unboundServersList
                    }
                }
            }
            .navigationTitle("选择服务器")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("登出") {
                        appState.logout()
                    }
                    .foregroundStyle(Theme.red)
                }
            }
            .refreshable {
                await refresh()
            }
        }
        .task {
            await refresh()
        }
    }

    // MARK: - 我的服务器列表

    private var myServersList: some View {
        ScrollView {
            if appState.myServers.isEmpty {
                emptyView("暂无绑定的服务器")
            } else {
                LazyVStack(spacing: 12) {
                    ForEach(appState.myServers) { server in
                        VStack(spacing: 0) {
                            serverCard(server)

                            // Owner展开审批请求
                            if server.role == "owner", expandedServer == server.server_id,
                               let requests = pendingRequests[server.server_id], !requests.isEmpty {
                                requestsList(requests, serverId: server.server_id)
                            }
                        }
                    }
                }
                .padding()
            }
        }
    }

    private func serverCard(_ server: UserServerInfo) -> some View {
        Button {
            appState.selectServer(server.server_id)
        } label: {
            HStack {
                Circle()
                    .fill(server.online ? Theme.online : Theme.offline)
                    .frame(width: 10, height: 10)

                VStack(alignment: .leading, spacing: 4) {
                    Text(server.name)
                        .font(.body.bold())
                        .foregroundStyle(Theme.textPrimary)
                    Text(server.server_id)
                        .font(.caption)
                        .foregroundStyle(Theme.textMuted)
                }

                Spacer()

                Text(server.role == "owner" ? "Owner" : "Admin")
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(server.role == "owner" ? Theme.orange.opacity(0.2) : Theme.primary.opacity(0.2))
                    .foregroundStyle(server.role == "owner" ? Theme.orange : Theme.primary)
                    .cornerRadius(6)

                // 待审批角标
                if server.role == "owner" {
                    let count = pendingRequests[server.server_id]?.count ?? 0
                    if count > 0 {
                        Button {
                            withAnimation {
                                expandedServer = expandedServer == server.server_id ? nil : server.server_id
                            }
                        } label: {
                            Text("\(count)")
                                .font(.caption2.bold())
                                .foregroundStyle(.white)
                                .padding(6)
                                .background(Theme.red)
                                .clipShape(Circle())
                        }
                    }
                }

                Image(systemName: "chevron.right")
                    .foregroundStyle(Theme.textMuted)
            }
            .padding()
            .background(Theme.cardBackground)
            .cornerRadius(12)
        }
    }

    // MARK: - 审批请求列表

    private func requestsList(_ requests: [BindRequest], serverId: String) -> some View {
        VStack(spacing: 8) {
            ForEach(requests) { req in
                HStack {
                    Image(systemName: "person.badge.plus")
                        .foregroundStyle(Theme.orange)
                    Text(req.username)
                        .foregroundStyle(Theme.textPrimary)
                    Spacer()
                    Button("批准") {
                        Task { await approveRequest(serverId: serverId, requestId: req.id) }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Theme.green)
                    .controlSize(.small)

                    Button("拒绝") {
                        Task { await rejectRequest(serverId: serverId, requestId: req.id) }
                    }
                    .buttonStyle(.bordered)
                    .tint(Theme.red)
                    .controlSize(.small)
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
            }
        }
        .padding(.vertical, 8)
        .background(Theme.cardBackground.opacity(0.5))
        .cornerRadius(0)
    }

    // MARK: - 未绑定服务器列表

    private var unboundServersList: some View {
        ScrollView {
            if appState.unboundServers.isEmpty {
                emptyView("暂无未绑定的服务器")
            } else {
                LazyVStack(spacing: 12) {
                    ForEach(appState.unboundServers) { server in
                        HStack {
                            Circle()
                                .fill(server.online ? Theme.online : Theme.offline)
                                .frame(width: 10, height: 10)

                            VStack(alignment: .leading, spacing: 4) {
                                Text(server.name)
                                    .font(.body.bold())
                                    .foregroundStyle(Theme.textPrimary)
                                Text(server.server_id)
                                    .font(.caption)
                                    .foregroundStyle(Theme.textMuted)
                            }

                            Spacer()

                            Button("绑定") {
                                Task { await bindServer(serverId: server.server_id) }
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(Theme.primary)
                            .controlSize(.small)
                        }
                        .padding()
                        .background(Theme.cardBackground)
                        .cornerRadius(12)
                    }
                }
                .padding()
            }
        }
    }

    // MARK: - 空状态

    private func emptyView(_ text: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "server.rack")
                .font(.system(size: 40))
                .foregroundStyle(Theme.textMuted)
            Text(text)
                .foregroundStyle(Theme.textMuted)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.top, 100)
    }

    // MARK: - 操作

    private func refresh() async {
        await appState.fetchMyServers()
        if appState.isAdmin {
            await appState.fetchUnboundServers()
        }
        // 加载各服务器的待审批请求
        for server in appState.myServers where server.role == "owner" {
            do {
                let resp = try await APIClient.shared.fetchBindRequests(serverId: server.server_id)
                pendingRequests[server.server_id] = resp.requests.filter { $0.status == "pending" }
            } catch {}
        }
    }

    private func bindServer(serverId: String) async {
        do {
            let _ = try await APIClient.shared.bindServer(serverId: serverId)
            await refresh()
        } catch {
            appState.error = error.localizedDescription
        }
    }

    private func approveRequest(serverId: String, requestId: Int) async {
        do {
            let _ = try await APIClient.shared.approveRequest(serverId: serverId, requestId: requestId)
            await refresh()
        } catch {
            appState.error = error.localizedDescription
        }
    }

    private func rejectRequest(serverId: String, requestId: Int) async {
        do {
            let _ = try await APIClient.shared.rejectRequest(serverId: serverId, requestId: requestId)
            await refresh()
        } catch {
            appState.error = error.localizedDescription
        }
    }
}
