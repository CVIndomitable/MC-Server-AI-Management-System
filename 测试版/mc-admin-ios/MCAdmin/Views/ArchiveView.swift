import SwiftUI

// MARK: - 档案馆主页

struct ArchiveView: View {
    @Environment(AppState.self) private var appState

    @State private var items: [SparkProfileSummary] = []
    @State private var total: Int = 0
    @State private var loading = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                if appState.serverId.isEmpty {
                    emptyState("未选择服务器", subtitle: "请先返回服务器选择页")
                } else if loading && items.isEmpty {
                    ProgressView().tint(Theme.primary)
                } else if items.isEmpty {
                    emptyState(
                        "还没有采样档案",
                        subtitle: "让 AI 执行 /spark profiler start 和 /spark profiler stop\n停止后系统会自动归档报告链接"
                    )
                } else {
                    ScrollView {
                        LazyVStack(spacing: 10) {
                            ForEach(items) { item in
                                NavigationLink {
                                    ArchiveDetailView(
                                        serverId: appState.serverId,
                                        profileId: item.id,
                                        onChanged: { await refresh() }
                                    )
                                } label: {
                                    ArchiveListRow(item: item)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding()
                    }
                }
            }
            .navigationTitle("档案馆")
            .navigationBarTitleDisplayMode(.inline)
            .refreshable { await refresh() }
            .task { await refresh() }
            .alert("错误", isPresented: .constant(errorMessage != nil)) {
                Button("好") { errorMessage = nil }
            } message: {
                Text(errorMessage ?? "")
            }
        }
    }

    private func emptyState(_ title: String, subtitle: String) -> some View {
        VStack(spacing: 10) {
            Image(systemName: "archivebox")
                .font(.system(size: 44))
                .foregroundStyle(Theme.textMuted)
            Text(title)
                .font(.headline)
                .foregroundStyle(Theme.textSecondary)
            Text(subtitle)
                .font(.footnote)
                .foregroundStyle(Theme.textMuted)
                .multilineTextAlignment(.center)
        }
        .padding(24)
    }

    private func refresh() async {
        guard !appState.serverId.isEmpty else { return }
        loading = true
        defer { loading = false }
        do {
            let resp = try await APIClient.shared.listSparkArchives(
                serverId: appState.serverId, limit: 50, offset: 0
            )
            items = resp.items
            total = resp.total
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

// MARK: - 列表行

private struct ArchiveListRow: View {
    let item: SparkProfileSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                statusBadge
                Text("#\(item.id)")
                    .font(.caption).monospaced()
                    .foregroundStyle(Theme.textMuted)
                Spacer()
                Text(formatStart)
                    .font(.caption)
                    .foregroundStyle(Theme.textMuted)
            }

            if let cmd = item.start_command {
                Text(cmd)
                    .font(.system(.footnote, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(1)
            }

            HStack(spacing: 12) {
                if item.profile_url != nil {
                    Label("已上传", systemImage: "link")
                        .font(.caption)
                        .foregroundStyle(Theme.cyan)
                        .lineLimit(1)
                } else if item.status == SparkProfileStatus.running {
                    Label("采样中", systemImage: "waveform")
                        .font(.caption)
                        .foregroundStyle(Theme.orange)
                } else {
                    Label("无链接", systemImage: "link.badge.plus")
                        .font(.caption)
                        .foregroundStyle(Theme.textMuted)
                }

                if item.analyzed_at != nil {
                    Label("已分析", systemImage: "sparkles")
                        .font(.caption)
                        .foregroundStyle(Theme.primary)
                }

                Spacer()
                if let dur = durationText {
                    Text(dur)
                        .font(.caption).monospaced()
                        .foregroundStyle(Theme.textMuted)
                }
            }
        }
        .padding(12)
        .background(Theme.cardBackground)
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private var statusBadge: some View {
        let (text, color): (String, Color) = {
            switch item.status {
            case SparkProfileStatus.running: return ("采样中", Theme.orange)
            case SparkProfileStatus.stopped: return ("待分析", Theme.textSecondary)
            case SparkProfileStatus.analyzing: return ("分析中", Theme.primary)
            case SparkProfileStatus.analyzed: return ("已分析", Theme.green)
            case SparkProfileStatus.failed: return ("失败", Theme.red)
            default: return (item.status, Theme.textMuted)
            }
        }()
        return Text(text)
            .font(.caption2).bold()
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.2))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }

    private var formatStart: String {
        // 后端返回 ISO8601 UTC，这里简单截到分钟
        let s = item.started_at
        let end = s.index(s.startIndex, offsetBy: min(16, s.count))
        return String(s[..<end]).replacingOccurrences(of: "T", with: " ")
    }

    private var durationText: String? {
        guard let stop = item.stopped_at else { return nil }
        let fmt = ISO8601DateFormatter()
        fmt.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let parseLoose: (String) -> Date? = { str in
            if let d = fmt.date(from: str) { return d }
            let alt = ISO8601DateFormatter()
            alt.formatOptions = [.withInternetDateTime]
            return alt.date(from: str)
        }
        guard let a = parseLoose(item.started_at), let b = parseLoose(stop) else { return nil }
        let sec = Int(b.timeIntervalSince(a))
        if sec < 60 { return "\(sec)s" }
        return "\(sec / 60)m\(sec % 60)s"
    }
}

// MARK: - 详情页

struct ArchiveDetailView: View {
    let serverId: String
    let profileId: Int
    let onChanged: () async -> Void

    @State private var detail: SparkProfileDetail?
    @State private var loading = false
    @State private var analyzing = false
    @State private var thinkingExpanded = false
    @State private var rawExpanded = false
    @State private var errorMessage: String?
    @State private var showDeleteConfirm = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            if let d = detail {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        headerCard(d)
                        if let url = d.profile_url {
                            urlCard(url)
                        }
                        analysisCard(d)
                        if let thinking = d.ai_thinking, !thinking.isEmpty {
                            thinkingCard(thinking)
                        }
                        if let raw = d.profile_raw, !raw.isEmpty {
                            rawCard(raw)
                        }
                        if let output = d.stop_output, !output.isEmpty {
                            stopOutputCard(output)
                        }
                    }
                    .padding()
                }
            } else if loading {
                ProgressView().tint(Theme.primary)
            } else {
                Text("加载失败").foregroundStyle(Theme.textMuted)
            }
        }
        .navigationTitle("档案 #\(profileId)")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button(role: .destructive) {
                        showDeleteConfirm = true
                    } label: {
                        Label("删除档案", systemImage: "trash")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
            }
        }
        .confirmationDialog("确定删除这份档案？", isPresented: $showDeleteConfirm) {
            Button("删除", role: .destructive) {
                Task { await delete() }
            }
            Button("取消", role: .cancel) {}
        }
        .task { await load() }
        .alert("错误", isPresented: .constant(errorMessage != nil)) {
            Button("好") { errorMessage = nil }
        } message: {
            Text(errorMessage ?? "")
        }
    }

    // MARK: - 卡片组件

    private func headerCard(_ d: SparkProfileDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(statusLabel(d.status))
                    .font(.caption).bold()
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .background(statusColor(d.status).opacity(0.2))
                    .foregroundStyle(statusColor(d.status))
                    .clipShape(Capsule())
                Spacer()
                if let model = d.ai_model {
                    Text(model)
                        .font(.caption2).monospaced()
                        .foregroundStyle(Theme.textMuted)
                }
            }
            labelRow("操作人", value: d.admin_id)
            labelRow("开始时间", value: d.started_at)
            if let stop = d.stopped_at {
                labelRow("停止时间", value: stop)
            }
            if let cmd = d.start_command {
                labelRow("启动命令", value: cmd, mono: true)
            }
            if let err = d.error, !err.isEmpty {
                Text("错误：\(err)")
                    .font(.caption)
                    .foregroundStyle(Theme.red)
            }
        }
        .padding(12)
        .background(Theme.cardBackground)
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func urlCard(_ url: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Spark 报告链接").font(.caption).foregroundStyle(Theme.textMuted)
            if let u = URL(string: url) {
                Link(destination: u) {
                    HStack {
                        Image(systemName: "safari")
                        Text(url).lineLimit(1).truncationMode(.middle)
                            .font(.system(.footnote, design: .monospaced))
                    }
                    .foregroundStyle(Theme.cyan)
                }
            } else {
                Text(url)
                    .font(.system(.footnote, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
            }
        }
        .padding(12)
        .background(Theme.cardBackground)
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func analysisCard(_ d: SparkProfileDetail) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("AI 分析", systemImage: "sparkles")
                    .font(.headline)
                    .foregroundStyle(Theme.primary)
                Spacer()
                Button {
                    Task { await runAnalyze() }
                } label: {
                    if analyzing {
                        HStack(spacing: 6) {
                            ProgressView().tint(.white)
                            Text("分析中…")
                        }
                    } else {
                        Label(d.ai_analysis == nil ? "开始分析" : "重新分析",
                              systemImage: "arrow.clockwise")
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.primary)
                .disabled(analyzing || d.profile_url == nil)
            }
            if d.profile_url == nil {
                Text("档案缺少 spark 报告链接（可能是 start 后未 stop 或 stop 输出未包含链接），无法分析。")
                    .font(.footnote)
                    .foregroundStyle(Theme.textMuted)
            } else if let analysis = d.ai_analysis, !analysis.isEmpty {
                MarkdownText(analysis)
                    .foregroundStyle(Theme.textPrimary)
            } else if analyzing {
                Text("正在调用大模型进行深度思考，通常 15–60 秒，请稍候…")
                    .font(.footnote)
                    .foregroundStyle(Theme.textMuted)
            } else {
                Text("还没有 AI 分析。点击右上角「开始分析」触发。")
                    .font(.footnote)
                    .foregroundStyle(Theme.textMuted)
            }
        }
        .padding(12)
        .background(Theme.cardBackground)
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func thinkingCard(_ thinking: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                thinkingExpanded.toggle()
            } label: {
                HStack {
                    Label("思维过程", systemImage: "brain")
                        .font(.headline)
                        .foregroundStyle(Theme.purple)
                    Spacer()
                    Image(systemName: thinkingExpanded ? "chevron.up" : "chevron.down")
                        .foregroundStyle(Theme.textMuted)
                }
            }
            .buttonStyle(.plain)
            if thinkingExpanded {
                Text(thinking)
                    .font(.system(.footnote, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
                    .textSelection(.enabled)
                    .padding(8)
                    .background(Theme.background)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
            } else {
                Text("点击展开查看模型内部推理轨迹")
                    .font(.caption)
                    .foregroundStyle(Theme.textMuted)
            }
        }
        .padding(12)
        .background(Theme.cardBackground)
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func rawCard(_ raw: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                rawExpanded.toggle()
            } label: {
                HStack {
                    Label("报告原文（截断）", systemImage: "doc.text")
                        .font(.headline)
                        .foregroundStyle(Theme.textSecondary)
                    Spacer()
                    Image(systemName: rawExpanded ? "chevron.up" : "chevron.down")
                        .foregroundStyle(Theme.textMuted)
                }
            }
            .buttonStyle(.plain)
            if rawExpanded {
                Text(raw)
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(Theme.textMuted)
                    .textSelection(.enabled)
            }
        }
        .padding(12)
        .background(Theme.cardBackground)
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func stopOutputCard(_ output: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("stop 命令输出").font(.caption).foregroundStyle(Theme.textMuted)
            Text(output)
                .font(.system(.caption2, design: .monospaced))
                .foregroundStyle(Theme.textSecondary)
                .textSelection(.enabled)
        }
        .padding(12)
        .background(Theme.cardBackground)
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func labelRow(_ label: String, value: String, mono: Bool = false) -> some View {
        HStack(alignment: .top) {
            Text(label).font(.caption).foregroundStyle(Theme.textMuted).frame(width: 70, alignment: .leading)
            Text(value)
                .font(mono ? .system(.footnote, design: .monospaced) : .footnote)
                .foregroundStyle(Theme.textPrimary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        }
    }

    private func statusLabel(_ s: String) -> String {
        switch s {
        case SparkProfileStatus.running: return "采样中"
        case SparkProfileStatus.stopped: return "待分析"
        case SparkProfileStatus.analyzing: return "分析中"
        case SparkProfileStatus.analyzed: return "已分析"
        case SparkProfileStatus.failed: return "失败"
        default: return s
        }
    }

    private func statusColor(_ s: String) -> Color {
        switch s {
        case SparkProfileStatus.running: return Theme.orange
        case SparkProfileStatus.stopped: return Theme.textSecondary
        case SparkProfileStatus.analyzing: return Theme.primary
        case SparkProfileStatus.analyzed: return Theme.green
        case SparkProfileStatus.failed: return Theme.red
        default: return Theme.textMuted
        }
    }

    // MARK: - 数据

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            detail = try await APIClient.shared.getSparkArchive(
                serverId: serverId, profileId: profileId
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func runAnalyze() async {
        analyzing = true
        defer { analyzing = false }
        do {
            let resp = try await APIClient.shared.analyzeSparkArchive(
                serverId: serverId, profileId: profileId
            )
            detail = resp.profile
            thinkingExpanded = (resp.profile.ai_thinking?.isEmpty == false)
            await onChanged()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func delete() async {
        do {
            _ = try await APIClient.shared.deleteSparkArchive(
                serverId: serverId, profileId: profileId
            )
            await onChanged()
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
