import SwiftUI

struct StatusView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                ScrollView {
                    if let status = appState.serverStatus {
                        VStack(spacing: 16) {
                            // 连接状态
                            connectionCard

                            // TPS
                            tpsCard(status)

                            // 内存
                            memoryCard(status)

                            // 在线玩家
                            playersCard(status)

                            // 近期错误
                            if !status.recent_errors.isEmpty {
                                errorsCard(status)
                            }
                        }
                        .padding()
                    } else {
                        VStack(spacing: 12) {
                            ProgressView()
                                .tint(Theme.primary)
                            Text("等待服务器数据...")
                                .foregroundStyle(Theme.textMuted)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .padding(.top, 100)
                    }
                }
            }
            .navigationTitle("服务器状态")
            .navigationBarTitleDisplayMode(.inline)
            .refreshable {
                await fetchStatus()
            }
        }
        .task {
            await fetchStatus()
        }
    }

    // MARK: - 连接状态卡片

    private var connectionCard: some View {
        HStack {
            Circle()
                .fill(appState.wsManager.isConnected ? Theme.online : Theme.red)
                .frame(width: 10, height: 10)
            Text(appState.wsManager.isConnected ? "实时连接正常" : "连接已断开")
                .font(.subheadline)
                .foregroundStyle(Theme.textPrimary)
            Spacer()
            if let status = appState.serverStatus, let update = status.last_update {
                Text("更新: \(update)")
                    .font(.caption2)
                    .foregroundStyle(Theme.textMuted)
            }
        }
        .padding()
        .background(Theme.cardBackground)
        .cornerRadius(12)
    }

    // MARK: - TPS卡片

    private func tpsCard(_ status: ServerStatus) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("TPS")
                .font(.headline)
                .foregroundStyle(Theme.textSecondary)

            HStack(alignment: .firstTextBaseline) {
                Text(String(format: "%.1f", status.tps))
                    .font(.system(size: 48, weight: .bold, design: .rounded))
                    .foregroundStyle(Theme.tpsColor(status.tps))

                Text("/ 20.0")
                    .font(.title3)
                    .foregroundStyle(Theme.textMuted)

                Spacer()

                tpsStatusLabel(status.tps)
            }

            // TPS进度条
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Theme.border)
                        .frame(height: 8)

                    RoundedRectangle(cornerRadius: 4)
                        .fill(Theme.tpsColor(status.tps))
                        .frame(width: geo.size.width * min(status.tps / 20.0, 1.0), height: 8)
                }
            }
            .frame(height: 8)
        }
        .padding()
        .background(Theme.cardBackground)
        .cornerRadius(12)
    }

    private func tpsStatusLabel(_ tps: Double) -> some View {
        let (text, color): (String, Color) = {
            if tps >= 19 { return ("流畅", Theme.green) }
            if tps >= 15 { return ("一般", Theme.orange) }
            return ("卡顿", Theme.red)
        }()

        return Text(text)
            .font(.caption.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(color.opacity(0.2))
            .foregroundStyle(color)
            .cornerRadius(6)
    }

    // MARK: - 内存卡片

    private func memoryCard(_ status: ServerStatus) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("内存")
                .font(.headline)
                .foregroundStyle(Theme.textSecondary)

            let percent = status.memory_max_mb > 0
                ? Double(status.memory_used_mb) / Double(status.memory_max_mb) * 100 : 0

            HStack {
                Text("\(status.memory_used_mb) MB")
                    .font(.title2.bold())
                    .foregroundStyle(Theme.textPrimary)
                Text("/ \(status.memory_max_mb) MB")
                    .font(.subheadline)
                    .foregroundStyle(Theme.textMuted)
                Spacer()
                Text(String(format: "%.0f%%", percent))
                    .font(.subheadline.bold())
                    .foregroundStyle(percent > 80 ? Theme.red : Theme.primary)
            }

            // 内存进度条
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Theme.border)
                        .frame(height: 8)

                    RoundedRectangle(cornerRadius: 4)
                        .fill(percent > 80 ? Theme.red : Theme.primary)
                        .frame(width: geo.size.width * min(percent / 100.0, 1.0), height: 8)
                }
            }
            .frame(height: 8)
        }
        .padding()
        .background(Theme.cardBackground)
        .cornerRadius(12)
    }

    // MARK: - 在线玩家卡片

    private func playersCard(_ status: ServerStatus) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("在线玩家")
                    .font(.headline)
                    .foregroundStyle(Theme.textSecondary)
                Spacer()
                Text("\(status.players.count)")
                    .font(.subheadline.bold())
                    .foregroundStyle(Theme.primary)
            }

            if status.players.isEmpty {
                Text("暂无在线玩家")
                    .font(.subheadline)
                    .foregroundStyle(Theme.textMuted)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 8)
            } else {
                LazyVGrid(columns: [
                    GridItem(.flexible()),
                    GridItem(.flexible()),
                ], spacing: 8) {
                    ForEach(status.players, id: \.self) { player in
                        HStack(spacing: 6) {
                            Image(systemName: "person.fill")
                                .font(.caption)
                                .foregroundStyle(Theme.green)
                            Text(player)
                                .font(.subheadline)
                                .foregroundStyle(Theme.textPrimary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                        .background(Theme.background)
                        .cornerRadius(8)
                    }
                }
            }
        }
        .padding()
        .background(Theme.cardBackground)
        .cornerRadius(12)
    }

    // MARK: - 错误日志卡片

    private func errorsCard(_ status: ServerStatus) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(Theme.orange)
                Text("近期错误")
                    .font(.headline)
                    .foregroundStyle(Theme.textSecondary)
            }

            ForEach(status.recent_errors, id: \.self) { error in
                Text(error)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(Theme.red)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.black.opacity(0.3))
                    .cornerRadius(6)
            }
        }
        .padding()
        .background(Theme.cardBackground)
        .cornerRadius(12)
    }

    // MARK: - 拉取状态

    private func fetchStatus() async {
        guard !appState.serverId.isEmpty else { return }
        do {
            appState.serverStatus = try await APIClient.shared.fetchStatus(serverId: appState.serverId)
        } catch {}
    }
}
