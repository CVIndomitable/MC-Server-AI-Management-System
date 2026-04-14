import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
  Modal,
  RefreshControl,
} from 'react-native';
import { useAppStore } from '../services/store';
import apiService from '../services/api';
import { UserInfo, ServerUserInfo } from '../types';

export default function SettingsScreen() {
  const { username, userRole, serverId, myServers, logout, fetchMyServers } = useAppStore();
  const currentServer = myServers.find(s => s.server_id === serverId);
  const isOwner = currentServer?.role === 'owner';
  const isSystemAdmin = userRole === 'admin';

  // 修改密码
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  // 用户管理
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newUserPassword, setNewUserPassword] = useState('');
  const [newUserRole, setNewUserRole] = useState<'admin' | 'user'>('user');

  // 服务器用户管理
  const [serverUsers, setServerUsers] = useState<ServerUserInfo[]>([]);
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [serverName, setServerName] = useState('');

  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    const promises: Promise<void>[] = [];

    if (isSystemAdmin) {
      promises.push(loadUsers());
    }
    if (serverId) {
      promises.push(loadServerUsers());
    }

    await Promise.all(promises);
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const loadUsers = async () => {
    const result = await apiService.listUsers();
    if (result.success && result.data) {
      setUsers(result.data.users);
    }
  };

  const loadServerUsers = async () => {
    const result = await apiService.listServerUsers(serverId);
    if (result.success && result.data) {
      setServerUsers(result.data.users);
    }
  };

  // ---- 修改密码 ----
  const handleChangePassword = async () => {
    if (newPassword.length < 6) {
      Alert.alert('提示', '新密码长度不能少于6位');
      return;
    }
    if (newPassword !== confirmPassword) {
      Alert.alert('提示', '两次输入的新密码不一致');
      return;
    }

    const result = await apiService.changePassword(oldPassword, newPassword);
    if (result.success) {
      Alert.alert('成功', '密码修改成功，请重新登录');
      setShowPasswordModal(false);
      logout();
    } else {
      Alert.alert('失败', result.error || '修改密码失败');
    }
  };

  // ---- 注册用户 ----
  const handleRegister = async () => {
    if (!newUsername.trim()) {
      Alert.alert('提示', '请输入用户名');
      return;
    }
    if (newUserPassword.length < 6) {
      Alert.alert('提示', '密码长度不能少于6位');
      return;
    }

    const result = await apiService.register(newUsername.trim(), newUserPassword, newUserRole);
    if (result.success) {
      Alert.alert('成功', `用户 ${newUsername} 创建成功`);
      setShowRegisterModal(false);
      setNewUsername('');
      setNewUserPassword('');
      setNewUserRole('user');
      await loadUsers();
    } else {
      Alert.alert('失败', result.error || '注册失败');
    }
  };

  // ---- 删除用户 ----
  const handleDeleteUser = (targetUsername: string) => {
    Alert.alert('确认删除', `确定要删除用户 ${targetUsername} 吗？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => {
          const result = await apiService.deleteUser(targetUsername);
          if (result.success) {
            Alert.alert('成功', `用户 ${targetUsername} 已删除`);
            await loadUsers();
          } else {
            Alert.alert('失败', result.error || '删除失败');
          }
        },
      },
    ]);
  };

  // ---- 重置密码 ----
  const [showResetModal, setShowResetModal] = useState(false);
  const [resetTargetUser, setResetTargetUser] = useState('');
  const [resetNewPassword, setResetNewPassword] = useState('');

  const handleResetPassword = (targetUsername: string) => {
    setResetTargetUser(targetUsername);
    setResetNewPassword('');
    setShowResetModal(true);
  };

  const confirmResetPassword = async () => {
    if (resetNewPassword.length < 6) {
      Alert.alert('提示', '密码长度不能少于6位');
      return;
    }
    const result = await apiService.resetPassword(resetTargetUser, resetNewPassword);
    setShowResetModal(false);
    if (result.success) {
      Alert.alert('成功', `用户 ${resetTargetUser} 的密码已重置`);
    } else {
      Alert.alert('失败', result.error || '重置失败');
    }
  };

  // ---- 修改服务器名 ----
  const handleRenameServer = async () => {
    if (!serverName.trim()) {
      Alert.alert('提示', '名称不能为空');
      return;
    }

    const result = await apiService.updateServerName(serverId, serverName.trim());
    if (result.success) {
      Alert.alert('成功', '服务器名称已更新');
      setShowRenameModal(false);
      await fetchMyServers();
    } else {
      Alert.alert('失败', result.error || '修改名称失败');
    }
  };

  // ---- 解绑用户 ----
  const handleUnbindUser = (targetUsername: string) => {
    Alert.alert('确认解绑', `确定要将 ${targetUsername} 从服务器解绑吗？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '解绑',
        style: 'destructive',
        onPress: async () => {
          const result = await apiService.unbindUser(serverId, targetUsername);
          if (result.success) {
            Alert.alert('成功', `已将 ${targetUsername} 从服务器解绑`);
            await loadServerUsers();
          } else {
            Alert.alert('失败', result.error || '解绑失败');
          }
        },
      },
    ]);
  };

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#007AFF" />}
    >
      {/* 当前用户信息 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>账号信息</Text>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>用户名</Text>
          <Text style={styles.infoValue}>{username}</Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>系统角色</Text>
          <Text style={[styles.infoValue, styles.roleBadge]}>
            {userRole === 'admin' ? '管理员' : '普通用户'}
          </Text>
        </View>
        {currentServer && (
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>服务器权限</Text>
            <Text style={[styles.infoValue, styles.roleBadge]}>
              {isOwner ? '主管理员' : '管理员'}
            </Text>
          </View>
        )}

        <TouchableOpacity
          style={styles.actionRow}
          onPress={() => {
            setOldPassword('');
            setNewPassword('');
            setConfirmPassword('');
            setShowPasswordModal(true);
          }}
        >
          <Text style={styles.actionText}>修改密码</Text>
          <Text style={styles.arrow}>&gt;</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.actionRow}
          onPress={() => {
            logout();
          }}
        >
          <Text style={styles.actionText}>切换账号</Text>
          <Text style={styles.arrow}>&gt;</Text>
        </TouchableOpacity>

        <TouchableOpacity style={[styles.actionRow, styles.dangerRow]} onPress={logout}>
          <Text style={styles.dangerText}>退出登录</Text>
        </TouchableOpacity>
      </View>

      {/* 服务器管理（选中服务器时显示） */}
      {serverId && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>
            服务器管理 - {currentServer?.name || serverId}
          </Text>

          {isOwner && (
            <TouchableOpacity
              style={styles.actionRow}
              onPress={() => {
                setServerName(currentServer?.name || '');
                setShowRenameModal(true);
              }}
            >
              <Text style={styles.actionText}>修改服务器名称</Text>
              <Text style={styles.arrow}>&gt;</Text>
            </TouchableOpacity>
          )}

          <Text style={styles.subTitle}>管理员列表 ({serverUsers.length})</Text>
          {serverUsers.map((user) => (
            <View key={user.username} style={styles.userRow}>
              <View style={styles.userInfo}>
                <Text style={styles.userName}>{user.username}</Text>
                <Text style={styles.userMeta}>
                  {user.role === 'owner' ? '主管理员' : '管理员'}
                  {' | '}
                  {new Date(user.bound_at).toLocaleDateString('zh-CN')}
                </Text>
              </View>
              {isOwner && user.role !== 'owner' && (
                <TouchableOpacity
                  style={styles.removeBtn}
                  onPress={() => handleUnbindUser(user.username)}
                >
                  <Text style={styles.removeBtnText}>解绑</Text>
                </TouchableOpacity>
              )}
            </View>
          ))}
        </View>
      )}

      {/* 系统用户管理（仅admin） */}
      {isSystemAdmin && (
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>用户管理</Text>
            <TouchableOpacity
              style={styles.addBtn}
              onPress={() => {
                setNewUsername('');
                setNewUserPassword('');
                setNewUserRole('user');
                setShowRegisterModal(true);
              }}
            >
              <Text style={styles.addBtnText}>+ 新增</Text>
            </TouchableOpacity>
          </View>

          {users.map((user) => (
            <View key={user.username} style={styles.userRow}>
              <View style={styles.userInfo}>
                <Text style={styles.userName}>{user.username}</Text>
                <Text style={styles.userMeta}>
                  {user.role === 'admin' ? '管理员' : '普通用户'}
                  {' | '}
                  {new Date(user.created_at).toLocaleDateString('zh-CN')}
                </Text>
              </View>
              {user.username !== username && (
                <View style={styles.userActions}>
                  <TouchableOpacity
                    style={styles.resetBtn}
                    onPress={() => handleResetPassword(user.username)}
                  >
                    <Text style={styles.resetBtnText}>重置密码</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.removeBtn}
                    onPress={() => handleDeleteUser(user.username)}
                  >
                    <Text style={styles.removeBtnText}>删除</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>
          ))}
        </View>
      )}

      <View style={{ height: 40 }} />

      {/* 修改密码弹窗 */}
      <Modal
        visible={showPasswordModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowPasswordModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>修改密码</Text>
            <TextInput
              style={styles.modalInput}
              placeholder="当前密码"
              placeholderTextColor="#888"
              secureTextEntry
              value={oldPassword}
              onChangeText={setOldPassword}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="新密码（至少6位）"
              placeholderTextColor="#888"
              secureTextEntry
              value={newPassword}
              onChangeText={setNewPassword}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="确认新密码"
              placeholderTextColor="#888"
              secureTextEntry
              value={confirmPassword}
              onChangeText={setConfirmPassword}
            />
            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={[styles.modalButton, styles.cancelButton]}
                onPress={() => setShowPasswordModal(false)}
              >
                <Text style={styles.buttonText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalButton, styles.confirmButton]}
                onPress={handleChangePassword}
              >
                <Text style={styles.buttonText}>确定</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* 注册用户弹窗 */}
      <Modal
        visible={showRegisterModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowRegisterModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>新增用户</Text>
            <TextInput
              style={styles.modalInput}
              placeholder="用户名"
              placeholderTextColor="#888"
              value={newUsername}
              onChangeText={setNewUsername}
              autoCapitalize="none"
            />
            <TextInput
              style={styles.modalInput}
              placeholder="密码（至少6位）"
              placeholderTextColor="#888"
              secureTextEntry
              value={newUserPassword}
              onChangeText={setNewUserPassword}
            />
            <View style={styles.roleSelector}>
              <TouchableOpacity
                style={[styles.roleOption, newUserRole === 'user' && styles.roleOptionActive]}
                onPress={() => setNewUserRole('user')}
              >
                <Text style={[styles.roleOptionText, newUserRole === 'user' && styles.roleOptionTextActive]}>
                  普通用户
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.roleOption, newUserRole === 'admin' && styles.roleOptionActive]}
                onPress={() => setNewUserRole('admin')}
              >
                <Text style={[styles.roleOptionText, newUserRole === 'admin' && styles.roleOptionTextActive]}>
                  管理员
                </Text>
              </TouchableOpacity>
            </View>
            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={[styles.modalButton, styles.cancelButton]}
                onPress={() => setShowRegisterModal(false)}
              >
                <Text style={styles.buttonText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalButton, styles.confirmButton]}
                onPress={handleRegister}
              >
                <Text style={styles.buttonText}>创建</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* 修改服务器名弹窗 */}
      <Modal
        visible={showRenameModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowRenameModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>修改服务器名称</Text>
            <TextInput
              style={styles.modalInput}
              placeholder="输入新名称"
              placeholderTextColor="#888"
              value={serverName}
              onChangeText={setServerName}
            />
            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={[styles.modalButton, styles.cancelButton]}
                onPress={() => setShowRenameModal(false)}
              >
                <Text style={styles.buttonText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalButton, styles.confirmButton]}
                onPress={handleRenameServer}
              >
                <Text style={styles.buttonText}>确定</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* 重置密码弹窗 */}
      <Modal
        visible={showResetModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowResetModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>重置 {resetTargetUser} 的密码</Text>
            <TextInput
              style={styles.modalInput}
              placeholder="新密码（至少6位）"
              placeholderTextColor="#888"
              secureTextEntry
              value={resetNewPassword}
              onChangeText={setResetNewPassword}
            />
            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={[styles.modalButton, styles.cancelButton]}
                onPress={() => setShowResetModal(false)}
              >
                <Text style={styles.buttonText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalButton, styles.confirmButton]}
                onPress={confirmResetPassword}
              >
                <Text style={styles.buttonText}>确定</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a1a',
  },
  section: {
    backgroundColor: '#2a2a2a',
    marginHorizontal: 12,
    marginTop: 12,
    borderRadius: 12,
    padding: 16,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  sectionTitle: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 12,
  },
  subTitle: {
    color: '#aaa',
    fontSize: 14,
    fontWeight: '600',
    marginTop: 12,
    marginBottom: 8,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#333',
  },
  infoLabel: {
    color: '#aaa',
    fontSize: 15,
  },
  infoValue: {
    color: '#fff',
    fontSize: 15,
  },
  roleBadge: {
    color: '#007AFF',
  },
  actionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#333',
  },
  actionText: {
    color: '#007AFF',
    fontSize: 15,
  },
  arrow: {
    color: '#555',
    fontSize: 16,
  },
  dangerRow: {
    borderBottomWidth: 0,
  },
  dangerText: {
    color: '#F44336',
    fontSize: 15,
  },
  userRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#333',
  },
  userInfo: {
    flex: 1,
  },
  userName: {
    color: '#fff',
    fontSize: 15,
  },
  userMeta: {
    color: '#888',
    fontSize: 12,
    marginTop: 2,
  },
  userActions: {
    flexDirection: 'row',
    gap: 6,
  },
  addBtn: {
    backgroundColor: '#007AFF',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    marginBottom: 12,
  },
  addBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  resetBtn: {
    backgroundColor: '#FF9800',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 6,
  },
  resetBtnText: {
    color: '#fff',
    fontSize: 12,
  },
  removeBtn: {
    backgroundColor: '#F44336',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 6,
  },
  removeBtnText: {
    color: '#fff',
    fontSize: 12,
  },
  // 弹窗
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContent: {
    width: '85%',
    backgroundColor: '#2a2a2a',
    borderRadius: 16,
    padding: 20,
  },
  modalTitle: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 16,
    textAlign: 'center',
  },
  modalInput: {
    backgroundColor: '#1a1a1a',
    borderRadius: 8,
    padding: 12,
    color: '#fff',
    fontSize: 16,
    marginBottom: 12,
  },
  roleSelector: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 16,
  },
  roleOption: {
    flex: 1,
    backgroundColor: '#3a3a3a',
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: 'center',
  },
  roleOptionActive: {
    backgroundColor: '#007AFF',
  },
  roleOptionText: {
    color: '#888',
    fontSize: 14,
  },
  roleOptionTextActive: {
    color: '#fff',
    fontWeight: '600',
  },
  modalButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  modalButton: {
    flex: 1,
    padding: 12,
    borderRadius: 8,
    marginHorizontal: 4,
  },
  cancelButton: {
    backgroundColor: '#555',
  },
  confirmButton: {
    backgroundColor: '#007AFF',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    textAlign: 'center',
  },
});
