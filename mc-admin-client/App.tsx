import React, { useEffect, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'expo-status-bar';
import { Text, View, ActivityIndicator, StyleSheet, TouchableOpacity } from 'react-native';

import LoginScreen from './src/screens/LoginScreen';
import ServerSelectScreen from './src/screens/ServerSelectScreen';
import ChatScreen from './src/screens/ChatScreen';
import StatusScreen from './src/screens/StatusScreen';
import ActionsScreen from './src/screens/ActionsScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import { useAppStore } from './src/services/store';

const Tab = createBottomTabNavigator();

function MainTabs() {
  const { clearServerSelection, serverId, showActionsTab } = useAppStore();

  return (
    <Tab.Navigator
      screenOptions={{
        tabBarStyle: {
          backgroundColor: '#2a2a2a',
          borderTopColor: '#333',
        },
        tabBarActiveTintColor: '#007AFF',
        tabBarInactiveTintColor: '#888',
        headerStyle: {
          backgroundColor: '#2a2a2a',
        },
        headerTintColor: '#fff',
        headerRight: () => (
          <TouchableOpacity
            style={{ marginRight: 12, paddingHorizontal: 8, paddingVertical: 4 }}
            onPress={clearServerSelection}
          >
            <Text style={{ color: '#007AFF', fontSize: 13 }}>切换服务器</Text>
          </TouchableOpacity>
        ),
      }}
    >
      <Tab.Screen
        name="Chat"
        component={ChatScreen}
        options={{
          title: '对话',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 24 }}>💬</Text>,
        }}
      />
      <Tab.Screen
        name="Status"
        component={StatusScreen}
        options={{
          title: '状态',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 24 }}>📊</Text>,
        }}
      />
      {showActionsTab && (
        <Tab.Screen
          name="Actions"
          component={ActionsScreen}
          options={{
            title: '操作',
            tabBarIcon: ({ color }) => <Text style={{ fontSize: 24 }}>⚡</Text>,
          }}
        />
      )}
      <Tab.Screen
        name="Settings"
        component={SettingsScreen}
        options={{
          title: '设置',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 24 }}>⚙️</Text>,
        }}
      />
    </Tab.Navigator>
  );
}

export default function App() {
  const { isAuthenticated, serverSelected, restoreSession } = useAppStore();
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const initApp = async () => {
      try {
        await restoreSession();
      } catch (error) {
        console.error('应用初始化失败:', error);
      } finally {
        setIsLoading(false);
      }
    };
    initApp();
  }, []);

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <StatusBar style="light" />
        <Text style={styles.loadingLogo}>⛏️</Text>
        <ActivityIndicator size="large" color="#007AFF" />
        <Text style={styles.loadingText}>加载中...</Text>
      </View>
    );
  }

  // 登录 → 选服务器 → 主界面
  if (!isAuthenticated) {
    return (
      <>
        <StatusBar style="light" />
        <LoginScreen onLoginSuccess={() => {}} />
      </>
    );
  }

  if (!serverSelected) {
    return (
      <>
        <StatusBar style="light" />
        <ServerSelectScreen onServerSelected={() => {}} />
      </>
    );
  }

  return (
    <>
      <StatusBar style="light" />
      <NavigationContainer>
        <MainTabs />
      </NavigationContainer>
    </>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    backgroundColor: '#1a1a1a',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingLogo: {
    fontSize: 64,
    marginBottom: 24,
  },
  loadingText: {
    color: '#888',
    fontSize: 16,
    marginTop: 16,
  },
});
