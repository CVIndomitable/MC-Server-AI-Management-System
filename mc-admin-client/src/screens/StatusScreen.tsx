import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Platform, RefreshControl } from 'react-native';
import { useAppStore } from '../services/store';
import apiService from '../services/api';

export default function StatusScreen() {
  const { serverStatus, wsConnected, serverId, updateServerStatus } = useAppStore();
  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    const result = await apiService.getServerStatus(serverId);
    if (result.success && result.data) {
      updateServerStatus(result.data);
    }
    setRefreshing(false);
  };

  if (!serverStatus) {
    return (
      <View style={styles.container}>
        <View style={styles.connectionStatus}>
          <View style={[styles.statusDot, wsConnected ? styles.connected : styles.disconnected]} />
          <Text style={styles.statusText}>
            {wsConnected ? '已连接' : '未连接'}
          </Text>
        </View>
        <Text style={styles.noDataText}>暂无服务器数据</Text>
      </View>
    );
  }

  const memoryRatio = serverStatus.memory_used_mb / serverStatus.memory_max_mb;
  const memoryPercent = (memoryRatio * 100).toFixed(1);
  const tpsColor = serverStatus.tps >= 19 ? '#4CAF50' : serverStatus.tps >= 15 ? '#FF9800' : '#F44336';

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#007AFF" />
      }
    >
      {/* 连接状态指示器 */}
      <View style={styles.connectionStatus}>
        <View style={[styles.statusDot, wsConnected ? styles.connected : styles.disconnected]} />
        <Text style={styles.statusText}>
          {wsConnected ? '实时连接' : '连接断开'}
        </Text>
      </View>

      {/* TPS显示 */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>服务器性能</Text>
        <View style={styles.tpsContainer}>
          <Text style={[styles.tpsValue, { color: tpsColor }]}>
            {serverStatus.tps.toFixed(1)}
          </Text>
          <Text style={styles.tpsLabel}>TPS</Text>
        </View>
        <Text style={styles.hint}>
          {serverStatus.tps >= 19 ? '运行流畅' : serverStatus.tps >= 15 ? '轻微卡顿' : '严重卡顿'}
        </Text>
      </View>

      {/* 内存使用 */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>内存使用</Text>
        <View style={styles.memoryBar}>
          <View style={[styles.memoryFill, { flex: memoryRatio }]} />
          <View style={{ flex: 1 - memoryRatio }} />
        </View>
        <Text style={styles.memoryText}>
          {serverStatus.memory_used_mb} MB / {serverStatus.memory_max_mb} MB ({memoryPercent}%)
        </Text>
      </View>

      {/* 在线玩家 */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>在线玩家 ({serverStatus.players.length})</Text>
        {serverStatus.players.length > 0 ? (
          <View style={styles.playerList}>
            {serverStatus.players.map((player, index) => (
              <View key={index} style={styles.playerItem}>
                <View style={styles.playerDot} />
                <Text style={styles.playerName}>{player}</Text>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.noPlayersText}>当前无玩家在线</Text>
        )}
      </View>

      {/* 最近错误 */}
      {serverStatus.recent_errors.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>最近错误</Text>
          {serverStatus.recent_errors.map((error, index) => (
            <Text key={index} style={styles.errorText}>
              {error}
            </Text>
          ))}
        </View>
      )}

      <Text style={styles.updateTime}>
        更新时间: {new Date(serverStatus.timestamp * 1000).toLocaleString('zh-CN')}
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a1a',
  },
  connectionStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    backgroundColor: '#2a2a2a',
    borderBottomWidth: 1,
    borderBottomColor: '#333',
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginRight: 8,
  },
  connected: {
    backgroundColor: '#4CAF50',
  },
  disconnected: {
    backgroundColor: '#F44336',
  },
  statusText: {
    color: '#aaa',
    fontSize: 14,
  },
  card: {
    backgroundColor: '#2a2a2a',
    margin: 12,
    padding: 16,
    borderRadius: 12,
  },
  cardTitle: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 12,
  },
  tpsContainer: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'center',
    marginVertical: 8,
  },
  tpsValue: {
    fontSize: 48,
    fontWeight: 'bold',
  },
  tpsLabel: {
    color: '#aaa',
    fontSize: 20,
    marginLeft: 8,
  },
  hint: {
    color: '#aaa',
    fontSize: 14,
    textAlign: 'center',
  },
  memoryBar: {
    flexDirection: 'row',
    height: 24,
    backgroundColor: '#1a1a1a',
    borderRadius: 12,
    overflow: 'hidden',
    marginBottom: 8,
  },
  memoryFill: {
    height: '100%',
    backgroundColor: '#007AFF',
  },
  memoryText: {
    color: '#aaa',
    fontSize: 14,
  },
  playerList: {
    marginTop: 8,
  },
  playerItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
  },
  playerDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#4CAF50',
    marginRight: 12,
  },
  playerName: {
    color: '#fff',
    fontSize: 16,
  },
  noPlayersText: {
    color: '#888',
    fontSize: 14,
    fontStyle: 'italic',
  },
  errorText: {
    color: '#F44336',
    fontSize: 13,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    marginBottom: 4,
  },
  noDataText: {
    color: '#888',
    fontSize: 16,
    textAlign: 'center',
    marginTop: 100,
  },
  updateTime: {
    color: '#666',
    fontSize: 12,
    textAlign: 'center',
    marginVertical: 16,
  },
});
