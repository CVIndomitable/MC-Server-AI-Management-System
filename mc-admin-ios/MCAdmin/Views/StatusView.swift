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

                            // CPU
                            if status.cpu_system != nil || status.cpu_process != nil {
                                cpuCard(status)
                            }

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
        VStack(spacing: 10) {
            // AI后端连接
            HStack {
                Circle()
                    .fill(appState.isBackendOnline ? Theme.online : Theme.red)
                    .frame(width: 10, height: 10)
                Text("AI后端")
                    .font(.subheadline)
                    .foregroundStyle(Theme.textPrimary)
                Text(appState.isBackendOnline ? "已连接" : "未连接")
                    .font(.caption)
                    .foregroundStyle(appState.isBackendOnline ? Theme.green : Theme.red)
                Spacer()
            }

            // MC服务器连接
            HStack {
                Circle()
                    .fill(appState.serverStatus?.online == true ? Theme.online : Theme.red)
                    .frame(width: 10, height: 10)
                Text("MC服务器")
                    .font(.subheadline)
                    .foregroundStyle(Theme.textPrimary)
                Text(appState.serverStatus?.online == true ? "在线" : "离线")
                    .font(.caption)
                    .foregroundStyle(appState.serverStatus?.online == true ? Theme.green : Theme.red)
                Spacer()
                if let status = appState.serverStatus, let update = status.last_update {
                    Text("更新: \(update)")
                        .font(.caption2)
                        .foregroundStyle(Theme.textMuted)
                }
            }

            // MC服务器离线时提示数据可能过期
            if appState.serverStatus?.online != true {
                HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.caption2)
                        .foregroundStyle(Theme.orange)
                    Text("模组未连接，显示的是最后一次上报的数��")
                        .font(.caption2)
                        .foregroundStyle(Theme.orange)
                }
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

    // MARK: - CPU卡片

    private func cpuCard(_ status: ServerStatus) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("CPU")
                    .font(.headline)
                    .foregroundStyle(Theme.textSecondary)
                Spacer()
                if let cores = status.cpu_cores {
                    Text("\(cores) 核心")
                        .font(.caption)
                        .foregroundStyle(Theme.textMuted)
                }
            }

            if let systemCpu = status.cpu_system {
                cpuRow(label: "系统", value: systemCpu)
            }

            if let processCpu = status.cpu_process {
                cpuRow(label: "MC进程", value: processCpu)
            }
        }
        .padding()
        .background(Theme.cardBackground)
        .cornerRadius(12)
    }

    private func cpuRow(label: String, value: Double) -> some View {
        VStack(spacing: 6) {
            HStack {
                Text(label)
                    .font(.subheadline)
                    .foregroundStyle(Theme.textMuted)
                Spacer()
                Text(String(format: "%.1f%%", value))
                    .font(.subheadline.bold())
                    .foregroundStyle(value > 80 ? Theme.red : value > 50 ? Theme.orange : Theme.primary)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Theme.border)
                        .frame(height: 8)

                    RoundedRectangle(cornerRadius: 4)
                        .fill(value > 80 ? Theme.red : value > 50 ? Theme.orange : Theme.primary)
                        .frame(width: geo.size.width * min(value / 100.0, 1.0), height: 8)
                }
            }
            .frame(height: 8)
        }
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
        await appState.fetchServerStatus()
    }
}
