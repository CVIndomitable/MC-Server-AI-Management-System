import SwiftUI

struct SettingsView: View {
    @Environment(AppState.self) private var appState
    @AppStorage("actionsTabEnabled") private var actionsTabEnabled = false

    // 改密码
    @State private var showChangePassword = false
    @State private var oldPassword = ""
    @State private var newPassword = ""
    @State private var confirmPassword = ""

    // 创建用户
    @State private var showCreateUser = false
    @State private var newUsername = ""
    @State private var newUserPassword = ""
    @State private var newUserRole = "user"

    // 服务器重命名
    @State private var showRename = false
    @State private var newServerName = ""

    // 重置密码
    @State private var showResetPassword = false
    @State private var resetUsername = ""
    @State private var resetNewPassword = ""

    // 数据
    @State private var serverUsers: [ServerUser] = []
    @State private var allUsers: [UserInfo] = []
    @State private var alertMessage = ""
    @State private var showAlert = false

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                List {
                    // 账号信息
                    accountSection

                    // 界面设置
                    interfaceSection

                    // 服务器管理（选中服务器时）
                    if appState.serverSelected {
                        serverSection
                    }

                    // 用户管理（管理员）
                    if appState.isAdmin {
                        userManagementSection
                        systemSection
                    }
                }
                .scrollContentBackground(.hidden)
                .listStyle(.insetGrouped)
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .alert(alertMessage, isPresented: $showAlert) {
                Button("确定") {}
            }
            .sheet(isPresented: $showChangePassword) { changePasswordSheet }
            .sheet(isPresented: $showCreateUser) { createUserSheet }
            .sheet(isPresented: $showRename) { renameSheet }
            .sheet(isPresented: $showResetPassword) { resetPasswordSheet }
        }
        .task { await loadData() }
    }

    // MARK: - 账号信息

    private var accountSection: some View {
        Section("账号信息") {
            HStack {
                Text("用户名")
                    .foregroundStyle(Theme.textSecondary)
                Spacer()
                Text(appState.username)
                    .foregroundStyle(Theme.textPrimary)
            }
            .listRowBackground(Theme.cardBackground)

            HStack {
                Text("系统角色")
                    .foregroundStyle(Theme.textSecondary)
                Spacer()
                Text(appState.userRole == "admin" ? "管理员" : "用户")
                    .foregroundStyle(Theme.primary)
            }
            .listRowBackground(Theme.cardBackground)

            if let role = appState.currentServerRole {
                HStack {
                    Text("服务器权限")
                        .foregroundStyle(Theme.textSecondary)
                    Spacer()
                    Text(role == "owner" ? "Owner" : "Admin")
                        .foregroundStyle(Theme.orange)
                }
                .listRowBackground(Theme.cardBackground)
            }

            Button("修改密码") { showChangePassword = true }
                .foregroundStyle(Theme.primary)
                .listRowBackground(Theme.cardBackground)

            Button("切换服务器") { appState.clearServerSelection() }
                .foregroundStyle(Theme.primary)
                .listRowBackground(Theme.cardBackground)

            Button("退出登录") { appState.logout() }
                .foregroundStyle(Theme.red)
                .listRowBackground(Theme.cardBackground)
        }
    }

    // MARK: - 界面设置

    private var interfaceSection: some View {
        Section("界面") {
            Toggle(isOn: $actionsTabEnabled) {
                Label("显示快捷操作", systemImage: "bolt.fill")
                    .foregroundStyle(Theme.textPrimary)
            }
            .tint(Theme.primary)
            .listRowBackground(Theme.cardBackground)
        }
    }

    // MARK: - 服务器管理

    private var serverSection: some View {
        Section("服务器管理") {
            if appState.isServerOwner {
                Button("重命名服务器") { showRename = true }
                    .foregroundStyle(Theme.primary)
                    .listRowBackground(Theme.cardBackground)
            }

            ForEach(serverUsers) { user in
                HStack {
                    Image(systemName: "person.fill")
                        .foregroundStyle(user.role == "owner" ? Theme.orange : Theme.primary)
                    Text(user.username)
                        .foregroundStyle(Theme.textPrimary)
                    Spacer()
                    Text(user.role == "owner" ? "Owner" : "Admin")
                        .font(.caption)
                        .foregroundStyle(Theme.textMuted)

                    if appState.isServerOwner && user.role != "owner" && user.username != appState.username {
                        Button {
                            Task { await unbindUser(username: user.username) }
                        } label: {
                            Image(systemName: "minus.circle.fill")
                                .foregroundStyle(Theme.red)
                        }
                    }
                }
                .listRowBackground(Theme.cardBackground)
            }
        }
    }

    // MARK: - 用户管理

    private var userManagementSection: some View {
        Section("用户管理") {
            Button {
                showCreateUser = true
            } label: {
                Label("添加用户", systemImage: "person.badge.plus")
                    .foregroundStyle(Theme.green)
            }
            .listRowBackground(Theme.cardBackground)

            ForEach(allUsers) { user in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(user.username)
                            .foregroundStyle(Theme.textPrimary)
                        Text(user.role == "admin" ? "管理员" : "用户")
                            .font(.caption)
                            .foregroundStyle(Theme.textMuted)
                    }

                    Spacer()

                    if user.username != appState.username {
                        Button {
                            resetUsername = user.username
                            resetNewPassword = ""
                            showResetPassword = true
                        } label: {
                            Image(systemName: "key")
                                .foregroundStyle(Theme.orange)
                        }

                        Button {
                            Task { await deleteUser(username: user.username) }
                        } label: {
                            Image(systemName: "trash")
                                .foregroundStyle(Theme.red)
                        }
                    }
                }
                .listRowBackground(Theme.cardBackground)
            }
        }
    }

    // MARK: - 系统管理（管理员）

    private var systemSection: some View {
        Section("系统管理") {
            NavigationLink {
                ProvidersView()
            } label: {
                Label("LLM 供应商", systemImage: "server.rack")
                    .foregroundStyle(Theme.primary)
            }
            .listRowBackground(Theme.cardBackground)
        }
    }

    // MARK: - 修改密码

    private var changePasswordSheet: some View {
        NavigationStack {
            Form {
                SecureField("当前密码", text: $oldPassword)
                SecureField("新密码", text: $newPassword)
                SecureField("确认新密码", text: $confirmPassword)
            }
            .scrollContentBackground(.hidden)
            .background(Theme.background)
            .navigationTitle("修改密码")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") {
                        showChangePassword = false
                        clearPasswordFields()
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("保存") {
                        Task { await changePassword() }
                    }
                    .disabled(oldPassword.isEmpty || newPassword.isEmpty || newPassword != confirmPassword)
                }
            }
        }
        .presentationDetents([.medium])
    }

    // MARK: - 创建用户

    private var createUserSheet: some View {
        NavigationStack {
            Form {
                TextField("用户名", text: $newUsername)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                SecureField("密码", text: $newUserPassword)
                Picker("角色", selection: $newUserRole) {
                    Text("用户").tag("user")
                    Text("管理员").tag("admin")
                }
            }
            .scrollContentBackground(.hidden)
            .background(Theme.background)
            .navigationTitle("添加用户")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") {
                        showCreateUser = false
                        newUsername = ""
                        newUserPassword = ""
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("创建") {
                        Task { await createUser() }
                    }
                    .disabled(newUsername.isEmpty || newUserPassword.isEmpty)
                }
            }
        }
        .presentationDetents([.medium])
    }

    // MARK: - 重命名服务器

    private var renameSheet: some View {
        NavigationStack {
            Form {
                TextField("新名称", text: $newServerName)
            }
            .scrollContentBackground(.hidden)
            .background(Theme.background)
            .navigationTitle("重命名服务器")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") {
                        showRename = false
                        newServerName = ""
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("保存") {
                        Task { await renameServer() }
                    }
                    .disabled(newServerName.isEmpty)
                }
            }
        }
        .presentationDetents([.height(200)])
    }

    // MARK: - 重置密码

    private var resetPasswordSheet: some View {
        NavigationStack {
            Form {
                HStack {
                    Text("用户")
                    Spacer()
                    Text(resetUsername)
                        .foregroundStyle(.secondary)
                }
                SecureField("新密码", text: $resetNewPassword)
            }
            .scrollContentBackground(.hidden)
            .background(Theme.background)
            .navigationTitle("重置密码")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") {
                        showResetPassword = false
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("重置") {
                        Task { await resetPassword() }
                    }
                    .disabled(resetNewPassword.isEmpty)
                }
            }
        }
        .presentationDetents([.height(250)])
    }

    // MARK: - 操作方法

    private func loadData() async {
        if appState.serverSelected {
            do {
                let resp = try await APIClient.shared.fetchServerUsers(serverId: appState.serverId)
                serverUsers = resp.users
            } catch {
                showAlertMessage("加载管理员列表失败: \(error.localizedDescription)")
            }
        }

        if appState.isAdmin {
            do {
                let resp = try await APIClient.shared.listUsers()
                allUsers = resp.users
            } catch {
                showAlertMessage("加载用户列表失败: \(error.localizedDescription)")
            }
        }
    }

    private func changePassword() async {
        do {
            let _ = try await APIClient.shared.changePassword(oldPassword: oldPassword, newPassword: newPassword)
            showChangePassword = false
            clearPasswordFields()
            showAlertMessage("密码修改成功")
        } catch {
            clearPasswordFields()
            showAlertMessage(error.localizedDescription)
        }
    }

    private func createUser() async {
        do {
            let _ = try await APIClient.shared.register(username: newUsername, password: newUserPassword, role: newUserRole)
            showCreateUser = false
            clearCreateUserFields()
            showAlertMessage("用户创建成功")
            await loadData()
        } catch {
            clearCreateUserFields()
            showAlertMessage(error.localizedDescription)
        }
    }

    private func deleteUser(username: String) async {
        do {
            let _ = try await APIClient.shared.deleteUser(username: username)
            showAlertMessage("用户已删除")
            await loadData()
        } catch {
            showAlertMessage(error.localizedDescription)
        }
    }

    private func resetPassword() async {
        do {
            let _ = try await APIClient.shared.resetPassword(username: resetUsername, newPassword: resetNewPassword)
            showResetPassword = false
            clearResetPasswordFields()
            showAlertMessage("密码已重置")
        } catch {
            clearResetPasswordFields()
            showAlertMessage(error.localizedDescription)
        }
    }

    private func renameServer() async {
        do {
            let _ = try await APIClient.shared.updateServerName(serverId: appState.serverId, name: newServerName)
            showRename = false
            newServerName = ""
            showAlertMessage("服务器已重命名")
            await appState.fetchMyServers()
        } catch {
            showAlertMessage(error.localizedDescription)
        }
    }

    private func unbindUser(username: String) async {
        do {
            let _ = try await APIClient.shared.unbindUser(serverId: appState.serverId, username: username)
            showAlertMessage("用户已解绑")
            await loadData()
        } catch {
            showAlertMessage(error.localizedDescription)
        }
    }

    private func clearPasswordFields() {
        oldPassword = ""
        newPassword = ""
        confirmPassword = ""
    }

    private func clearCreateUserFields() {
        newUsername = ""
        newUserPassword = ""
    }

    private func clearResetPasswordFields() {
        resetUsername = ""
        resetNewPassword = ""
    }

    private func showAlertMessage(_ msg: String) {
        alertMessage = msg
        showAlert = true
    }
}
