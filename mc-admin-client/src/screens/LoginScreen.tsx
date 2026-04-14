import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ScrollView,
} from 'react-native';
import { useAppStore } from '../services/store';

interface LoginScreenProps {
  onLoginSuccess: () => void;
}

export default function LoginScreen({ onLoginSuccess }: LoginScreenProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showManualLogin, setShowManualLogin] = useState(false);
  const { login, quickLogin, isLoading, savedAccounts, loadSavedAccounts, removeSavedAccount } = useAppStore();

  useEffect(() => {
    loadSavedAccounts();
  }, []);

  const hasSavedAccounts = savedAccounts.length > 0;

  const handleLogin = async () => {
    if (!username.trim() || !password.trim()) {
      Alert.alert('错误', '请输入用户名和密码');
      return;
    }

    const success = await login(username, password);
    if (success) {
      onLoginSuccess();
    } else {
      Alert.alert('登录失败', '用户名或密码错误');
    }
  };

  const handleQuickLogin = async (accountUsername: string) => {
    const success = await quickLogin(accountUsername);
    if (success) {
      onLoginSuccess();
    } else {
      Alert.alert('登录失败', '保存的密码已失效，请重新输入密码');
      setUsername(accountUsername);
      setPassword('');
      setShowManualLogin(true);
    }
  };

  const handleRemoveAccount = (accountUsername: string) => {
    Alert.alert(
      '移除账号',
      `确定要移除已保存的账号 "${accountUsername}" 吗？`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '移除',
          style: 'destructive',
          onPress: () => removeSavedAccount(accountUsername),
        },
      ],
    );
  };

  const formatLastUsed = (timestamp: number) => {
    const diff = Date.now() - timestamp;
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes}分钟前`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}小时前`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}天前`;
    return new Date(timestamp).toLocaleDateString('zh-CN');
  };

  // 有保存的账号且未点击手动登录 → 显示账号列表
  if (hasSavedAccounts && !showManualLogin) {
    return (
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView contentContainerStyle={styles.scrollContent}>
          <Text style={styles.logo}>⛏️</Text>
          <Text style={styles.title}>MC Admin</Text>
          <Text style={styles.subtitle}>选择账号登录</Text>

          <View style={styles.accountList}>
            {savedAccounts.map((account) => (
              <TouchableOpacity
                key={account.username}
                style={styles.accountCard}
                onPress={() => handleQuickLogin(account.username)}
                onLongPress={() => handleRemoveAccount(account.username)}
                disabled={isLoading}
              >
                <View style={styles.accountAvatar}>
                  <Text style={styles.avatarText}>
                    {account.username.charAt(0).toUpperCase()}
                  </Text>
                </View>
                <View style={styles.accountInfo}>
                  <Text style={styles.accountName}>{account.username}</Text>
                  <Text style={styles.accountMeta}>
                    上次登录: {formatLastUsed(account.lastUsed)}
                  </Text>
                </View>
                <Text style={styles.accountArrow}>›</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TouchableOpacity
            style={styles.otherAccountBtn}
            onPress={() => {
              setUsername('');
              setPassword('');
              setShowManualLogin(true);
            }}
            disabled={isLoading}
          >
            <Text style={styles.otherAccountIcon}>+</Text>
            <Text style={styles.otherAccountText}>使用其他账号登录</Text>
          </TouchableOpacity>

          {isLoading && (
            <Text style={styles.loadingText}>登录中...</Text>
          )}

          <Text style={styles.hintText}>长按账号可移除</Text>
        </ScrollView>
      </KeyboardAvoidingView>
    );
  }

  // 无保存账号 或 点击了手动登录 → 显示登录表单
  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={styles.content}>
        <Text style={styles.logo}>⛏️</Text>
        <Text style={styles.title}>MC Admin</Text>
        <Text style={styles.subtitle}>服务器管理助手</Text>

        <View style={styles.form}>
          <TextInput
            style={styles.input}
            placeholder="用户名"
            placeholderTextColor="#888"
            value={username}
            onChangeText={setUsername}
            autoCapitalize="none"
            editable={!isLoading}
          />

          <TextInput
            style={styles.input}
            placeholder="密码"
            placeholderTextColor="#888"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            editable={!isLoading}
          />

          <TouchableOpacity
            style={[styles.loginButton, isLoading && styles.loginButtonDisabled]}
            onPress={handleLogin}
            disabled={isLoading}
          >
            <Text style={styles.loginButtonText}>
              {isLoading ? '登录中...' : '登录'}
            </Text>
          </TouchableOpacity>

          {hasSavedAccounts && (
            <TouchableOpacity
              style={styles.backToAccountsBtn}
              onPress={() => setShowManualLogin(false)}
              disabled={isLoading}
            >
              <Text style={styles.backToAccountsText}>返回账号列表</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a1a',
  },
  scrollContent: {
    flexGrow: 1,
    alignItems: 'center',
    paddingTop: 80,
    paddingBottom: 40,
    paddingHorizontal: 20,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  logo: {
    fontSize: 80,
    marginBottom: 16,
  },
  title: {
    color: '#fff',
    fontSize: 32,
    fontWeight: 'bold',
    marginBottom: 8,
  },
  subtitle: {
    color: '#888',
    fontSize: 16,
    marginBottom: 32,
  },
  // 账号列表
  accountList: {
    width: '100%',
    maxWidth: 400,
    marginBottom: 20,
  },
  accountCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#2a2a2a',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
  },
  accountAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  avatarText: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '700',
  },
  accountInfo: {
    flex: 1,
  },
  accountName: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '600',
  },
  accountMeta: {
    color: '#888',
    fontSize: 13,
    marginTop: 2,
  },
  accountArrow: {
    color: '#555',
    fontSize: 24,
    marginLeft: 8,
  },
  otherAccountBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#2a2a2a',
    borderRadius: 12,
    padding: 14,
    width: '100%',
    maxWidth: 400,
    borderWidth: 1,
    borderColor: '#3a3a3a',
    borderStyle: 'dashed',
  },
  otherAccountIcon: {
    color: '#007AFF',
    fontSize: 20,
    fontWeight: '600',
    marginRight: 8,
  },
  otherAccountText: {
    color: '#007AFF',
    fontSize: 15,
    fontWeight: '500',
  },
  loadingText: {
    color: '#007AFF',
    fontSize: 14,
    marginTop: 16,
  },
  hintText: {
    color: '#555',
    fontSize: 12,
    marginTop: 20,
  },
  // 登录表单
  form: {
    width: '100%',
    maxWidth: 400,
  },
  input: {
    backgroundColor: '#2a2a2a',
    borderRadius: 12,
    padding: 16,
    color: '#fff',
    fontSize: 16,
    marginBottom: 16,
  },
  loginButton: {
    backgroundColor: '#007AFF',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginTop: 8,
  },
  loginButtonDisabled: {
    backgroundColor: '#555',
  },
  loginButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
  backToAccountsBtn: {
    alignItems: 'center',
    marginTop: 16,
    padding: 12,
  },
  backToAccountsText: {
    color: '#007AFF',
    fontSize: 15,
  },
});
