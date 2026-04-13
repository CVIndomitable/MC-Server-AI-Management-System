import React, { useEffect, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'expo-status-bar';
import { Text, View, ActivityIndicator, StyleSheet } from 'react-native';

import LoginScreen from './src/screens/LoginScreen';
import ChatScreen from './src/screens/ChatScreen';
import StatusScreen from './src/screens/StatusScreen';
import ActionsScreen from './src/screens/ActionsScreen';
import { useAppStore } from './src/services/store';

const Tab = createBottomTabNavigator();

function MainTabs() {
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
      <Tab.Screen
        name="Actions"
        component={ActionsScreen}
        options={{
          title: '操作',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 24 }}>⚡</Text>,
        }}
      />
    </Tab.Navigator>
  );
}

export default function App() {
  const { isAuthenticated, restoreSession } = useAppStore();
  const [showMain, setShowMain] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // 启动时恢复会话
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

  useEffect(() => {
    if (isAuthenticated) {
      setShowMain(true);
    }
  }, [isAuthenticated]);

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

  return (
    <>
      <StatusBar style="light" />
      <NavigationContainer>
        {showMain ? (
          <MainTabs />
        ) : (
          <LoginScreen onLoginSuccess={() => setShowMain(true)} />
        )}
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
