import SwiftUI

struct ProvidersView: View {
    @State private var providers: [ApiProvider] = []
    @State private var loading = true
    @State private var alertMessage = ""
    @State private var showAlert = false
    @State private var editingProvider: ApiProvider?
    @State private var showEditor = false

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()

            List {
                Section {
                    Button {
                        editingProvider = nil
                        showEditor = true
                    } label: {
                        Label("新增供应商", systemImage: "plus.circle.fill")
                            .foregroundStyle(Theme.green)
                    }
                    .listRowBackground(Theme.cardBackground)
                }

                Section(header: Text("已配置（按优先级升序，数字小=优先）")) {
                    if loading {
                        HStack {
                            ProgressView()
                            Text("加载中…").foregroundStyle(Theme.textMuted)
                        }
                        .listRowBackground(Theme.cardBackground)
                    } else if providers.isEmpty {
                        Text("（暂无）")
                            .foregroundStyle(Theme.textMuted)
                            .listRowBackground(Theme.cardBackground)
                    } else {
                        ForEach(providers) { p in
                            ProviderRow(provider: p)
                                .listRowBackground(Theme.cardBackground)
                                .contentShape(Rectangle())
                                .onTapGesture {
                                    editingProvider = p
                                    showEditor = true
                                }
                                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                                    Button(role: .destructive) {
                                        Task { await delete(p) }
                                    } label: { Label("删除", systemImage: "trash") }
                                }
                        }
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .listStyle(.insetGrouped)
        }
        .navigationTitle("LLM 供应商")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .refreshable { await load() }
        .alert(alertMessage, isPresented: $showAlert) {
            Button("确定") {}
        }
        .sheet(isPresented: $showEditor) {
            ProviderEditorSheet(
                provider: editingProvider,
                onDone: { ok in
                    showEditor = false
                    if ok { Task { await load() } }
                }
            )
        }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            let resp = try await APIClient.shared.listProviders()
            providers = resp.providers
        } catch {
            show("加载失败: \(error.localizedDescription)")
        }
    }

    private func delete(_ p: ApiProvider) async {
        do {
            _ = try await APIClient.shared.deleteProvider(id: p.id)
            await load()
        } catch {
            show("删除失败: \(error.localizedDescription)")
        }
    }

    private func show(_ msg: String) {
        alertMessage = msg
        showAlert = true
    }
}

// MARK: - 行

private struct ProviderRow: View {
    let provider: ApiProvider

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: provider.enabled ? "bolt.fill" : "bolt.slash")
                    .foregroundStyle(provider.enabled ? Theme.green : Theme.textMuted)
                Text(provider.name)
                    .font(.body.bold())
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                Text("优先级 \(provider.priority)")
                    .font(.caption.monospacedDigit())
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Theme.primary.opacity(0.2))
                    .foregroundStyle(Theme.primary)
                    .cornerRadius(4)
            }

            Text(provider.base_url)
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(1)

            HStack(spacing: 6) {
                Text("key …\(provider.api_key_tail)")
                    .font(.caption2.monospaced())
                    .foregroundStyle(Theme.textMuted)
                if let m = provider.model_map, !m.isEmpty {
                    Text("映射 \(m.count) 项")
                        .font(.caption2)
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(Theme.orange.opacity(0.2))
                        .foregroundStyle(Theme.orange)
                        .cornerRadius(3)
                } else {
                    Text("无映射")
                        .font(.caption2)
                        .foregroundStyle(Theme.textMuted)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

// MARK: - 编辑/新增 Sheet

struct ProviderEditorSheet: View {
    let provider: ApiProvider?  // nil = 新增
    let onDone: (Bool) -> Void

    @State private var name = ""
    @State private var baseUrl = ""
    @State private var apiKey = ""
    @State private var priority = 100
    @State private var enabled = true
    @State private var mapEntries: [MapEntry] = []
    @State private var saving = false
    @State private var errorMsg: String?

    private var isEdit: Bool { provider != nil }

    var body: some View {
        NavigationStack {
            Form {
                Section("基本") {
                    TextField("名称（唯一）", text: $name)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                    TextField("base_url（如 https://api.xxx.com/anthropic）", text: $baseUrl)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                    SecureField(isEdit ? "API Key（留空不改）" : "API Key", text: $apiKey)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                    Stepper("优先级: \(priority)（数字小=优先）", value: $priority, in: 1...1000, step: 1)
                    Toggle("启用", isOn: $enabled)
                }

                Section(header: Text("模型映射"), footer: Text("canonical 模型名（如 mimo-v2-flash）→ 该 provider 实际模型名（如 claude-3-haiku-20240307）。留空则原样透传。")) {
                    ForEach($mapEntries) { $entry in
                        HStack {
                            TextField("canonical", text: $entry.canonical)
                                .autocorrectionDisabled()
                                .textInputAutocapitalization(.never)
                                .font(.caption.monospaced())
                            Image(systemName: "arrow.right")
                                .foregroundStyle(Theme.textMuted)
                                .font(.caption)
                            TextField("actual", text: $entry.actual)
                                .autocorrectionDisabled()
                                .textInputAutocapitalization(.never)
                                .font(.caption.monospaced())
                        }
                    }
                    .onDelete { idx in mapEntries.remove(atOffsets: idx) }

                    Button {
                        mapEntries.append(MapEntry())
                    } label: {
                        Label("新增一条映射", systemImage: "plus")
                    }
                }

                if let err = errorMsg {
                    Section { Text(err).foregroundStyle(Theme.red) }
                }
            }
            .navigationTitle(isEdit ? "编辑供应商" : "新增供应商")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") { onDone(false) }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(saving ? "保存中…" : "保存") {
                        Task { await save() }
                    }
                    .disabled(saving || !isValid)
                }
            }
        }
        .onAppear { load() }
    }

    private var isValid: Bool {
        let nameOk = !name.trimmingCharacters(in: .whitespaces).isEmpty
        let urlOk = !baseUrl.trimmingCharacters(in: .whitespaces).isEmpty
        let keyOk = isEdit || !apiKey.isEmpty
        return nameOk && urlOk && keyOk
    }

    private func load() {
        guard let p = provider else { return }
        name = p.name
        baseUrl = p.base_url
        priority = p.priority
        enabled = p.enabled
        if let m = p.model_map {
            mapEntries = m.map { MapEntry(canonical: $0.key, actual: $0.value) }
                .sorted { $0.canonical < $1.canonical }
        }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        errorMsg = nil

        var map: [String: String] = [:]
        for e in mapEntries {
            let k = e.canonical.trimmingCharacters(in: .whitespaces)
            let v = e.actual.trimmingCharacters(in: .whitespaces)
            if !k.isEmpty && !v.isEmpty { map[k] = v }
        }
        let mapToSend: [String: String]? = map.isEmpty ? nil : map
        let clearMap = isEdit && map.isEmpty  // 编辑时清空→清空映射

        do {
            if let p = provider {
                let req = ProviderUpdateRequest(
                    name: name,
                    base_url: baseUrl,
                    api_key: apiKey.isEmpty ? nil : apiKey,
                    priority: priority,
                    enabled: enabled,
                    model_map: mapToSend,
                    clear_model_map: clearMap
                )
                _ = try await APIClient.shared.updateProvider(id: p.id, req: req)
            } else {
                let req = ProviderCreateRequest(
                    name: name,
                    base_url: baseUrl,
                    api_key: apiKey,
                    priority: priority,
                    enabled: enabled,
                    model_map: mapToSend
                )
                _ = try await APIClient.shared.createProvider(req)
            }
            onDone(true)
        } catch {
            errorMsg = error.localizedDescription
        }
    }
}

private struct MapEntry: Identifiable {
    let id = UUID()
    var canonical: String = ""
    var actual: String = ""
}
