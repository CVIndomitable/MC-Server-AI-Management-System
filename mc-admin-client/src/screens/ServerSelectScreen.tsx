import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
  Alert,
  RefreshControl,
} from 'react-native';
import { useAppStore } from '../services/store';
import { UserServerInfo, ServerInfo, BindRequestInfo } from '../types';
import apiService from '../services/api';

interface Props {
  onServerSelected: () => void;
}

export default function ServerSelectScreen({ onServerSelected }: Props) {
  const {
    myServers,
    unboundServers,
    fetchMyServers,
    fetchUnboundServers,
    selectServer,
    bindServer,
    logout,
  } = useAppStore();

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showUnbound, setShowUnbound] = useState(false);
  // 审批相关
  const [pendingRequests, setPendingRequests] = useState<Record<string, BindRequestInfo[]>>({});

  const loadData = async () => {
    await Promise.all([fetchMyServers(), fetchUnboundServers()]);
    setLoading(false);
  };

  // 加载拥有的服务器的待审批申请
  const loadPendingRequests = async () => {
    const ownerServers = myServers.filter(s => s.role === 'owner');
    const requests: Record<string, BindRequestInfo[]> = {};
    for (const server of ownerServers) {
      const result = await apiService.getBindRequests(server.server_id);
      if (result.success && result.data) {
        const pending = result.data.requests;
        if (pending.length > 0) {
          requests[server.server_id] = pending;
        }
      }
    }
    setPendingRequests(requests);
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (myServers.length > 0) {
      loadPendingRequests();
    }
  }, [myServers]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const handleSelectServer = (serverId: string) => {
    selectServer(serverId);
    onServerSelected();
  };

  const handleBindServer = async (serverId: string) => {
    const result = await bindServer(serverId);
    if (result.success) {
      Alert.alert('绑定成功', '你已成为该服务器的主管理员');
      await loadData();
    } else {
      Alert.alert('提示', result.error || '绑定失败');
      await loadData();
    }
  };

  const handleApprove = async (serverId: string, requestId: number) => {
    const result = await apiService.approveBindRequest(serverId, requestId);
    if (result.success) {
      Alert.alert('已批准', '管理员已成功绑定');
      await loadData();
    } else {
      Alert.alert('失败', result.error || '审批失败');
    }
  };

  const handleReject = async (serverId: string, requestId: number) => {
    Alert.alert('确认拒绝', '确定要拒绝该绑定申请吗？', [
      { text: '取消', style: 'cancel' },
      {
        text: '拒绝',
        style: 'destructive',
        onPress: async () => {
          const result = await apiService.rejectBindRequest(serverId, requestId);
          if (result.success) {
            Alert.alert('已拒绝');
            await loadData();
          } else {
            Alert.alert('失败', result.error || '操作失败');
          }
        },
      },
    ]);
  };

  const totalPendingCount = Object.values(pendingRequests).reduce(
    (sum, reqs) => sum + reqs.length,
    0
  );

  const renderMyServer = ({ item }: { item: UserServerInfo }) => {
    const reqs = pendingRequests[item.server_id] || [];
    return (
      <View style={styles.serverCard}>
        <TouchableOpacity
          style={styles.serverCardMain}
          onPress={() => handleSelectServer(item.server_id)}
        >
          <View style={styles.serverHeader}>
            <Text style={styles.serverName}>{item.name || item.server_id}</Text>
            <View style={[styles.statusDot, item.online ? styles.online : styles.offline]} />
          </View>
          <View style={styles.serverMeta}>
            <Text style={styles.roleBadge}>
              {item.role === 'owner' ? '主管理员' : '管理员'}
            </Text>
            <Text style={styles.serverId}>{item.server_id}</Text>
          </View>
        </TouchableOpacity>

        {reqs.length > 0 && (
          <View style={styles.requestsSection}>
            <Text style={styles.requestsTitle}>待审批申请 ({reqs.length})</Text>
            {reqs.map(req => (
              <View key={req.id} style={styles.requestRow}>
                <Text style={styles.requestUser}>{req.username}</Text>
                <View style={styles.requestActions}>
                  <TouchableOpacity
                    style={styles.approveBtn}
                    onPress={() => handleApprove(item.server_id, req.id)}
                  >
                    <Text style={styles.approveBtnText}>批准</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.rejectBtn}
                    onPress={() => handleReject(item.server_id, req.id)}
                  >
                    <Text style={styles.rejectBtnText}>拒绝</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        )}
      </View>
    );
  };

  const renderUnboundServer = ({ item }: { item: ServerInfo }) => (
    <View style={styles.serverCard}>
      <View style={styles.serverCardMain}>
        <View style={styles.serverHeader}>
          <Text style={styles.serverName}>{item.server_id}</Text>
          <View style={[styles.statusDot, item.online ? styles.online : styles.offline]} />
        </View>
        <Text style={styles.serverTime}>
          注册时间: {new Date(item.created_at).toLocaleString()}
        </Text>
      </View>
      <TouchableOpacity
        style={styles.bindButton}
        onPress={() => handleBindServer(item.server_id)}
      >
        <Text style={styles.bindButtonText}>绑定</Text>
      </TouchableOpacity>
    </View>
  );

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#007AFF" />
        <Text style={styles.loadingText}>加载服务器列表...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>选择服务器</Text>
        <TouchableOpacity onPress={logout}>
          <Text style={styles.logoutText}>退出登录</Text>
        </TouchableOpacity>
      </View>

      {/* Tab切换 */}
      <View style={styles.tabs}>
        <TouchableOpacity
          style={[styles.tab, !showUnbound && styles.tabActive]}
          onPress={() => setShowUnbound(false)}
        >
          <Text style={[styles.tabText, !showUnbound && styles.tabTextActive]}>
            我的服务器 ({myServers.length})
          </Text>
          {totalPendingCount > 0 && (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{totalPendingCount}</Text>
            </View>
          )}
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, showUnbound && styles.tabActive]}
          onPress={() => setShowUnbound(true)}
        >
          <Text style={[styles.tabText, showUnbound && styles.tabTextActive]}>
            未绑定 ({unboundServers.length})
          </Text>
        </TouchableOpacity>
      </View>

      {!showUnbound ? (
        myServers.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyText}>你还没有绑定任何服务器</Text>
            <Text style={styles.emptyHint}>切换到"未绑定"标签绑定服务器</Text>
          </View>
        ) : (
          <FlatList
            data={myServers}
            keyExtractor={item => item.server_id}
            renderItem={renderMyServer}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#007AFF" />}
            contentContainerStyle={styles.list}
          />
        )
      ) : unboundServers.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyText}>没有未绑定的服务器</Text>
          <Text style={styles.emptyHint}>等待MC服务器模组连接后会自动出现</Text>
        </View>
      ) : (
        <FlatList
          data={unboundServers}
          keyExtractor={item => item.server_id}
          renderItem={renderUnboundServer}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#007AFF" />}
          contentContainerStyle={styles.list}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a1a',
    paddingTop: 60,
  },
  centered: {
    flex: 1,
    backgroundColor: '#1a1a1a',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    color: '#888',
    marginTop: 12,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    marginBottom: 16,
  },
  title: {
    color: '#fff',
    fontSize: 28,
    fontWeight: 'bold',
  },
  logoutText: {
    color: '#ff4444',
    fontSize: 14,
  },
  tabs: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    marginBottom: 12,
    gap: 12,
  },
  tab: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 20,
    backgroundColor: '#2a2a2a',
  },
  tabActive: {
    backgroundColor: '#007AFF',
  },
  tabText: {
    color: '#888',
    fontSize: 14,
  },
  tabTextActive: {
    color: '#fff',
  },
  badge: {
    backgroundColor: '#ff4444',
    borderRadius: 10,
    minWidth: 20,
    height: 20,
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 6,
    paddingHorizontal: 4,
  },
  badgeText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: 'bold',
  },
  list: {
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  serverCard: {
    backgroundColor: '#2a2a2a',
    borderRadius: 12,
    marginBottom: 12,
    overflow: 'hidden',
  },
  serverCardMain: {
    padding: 16,
  },
  serverHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  serverName: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
    flex: 1,
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginLeft: 8,
  },
  online: {
    backgroundColor: '#34C759',
  },
  offline: {
    backgroundColor: '#666',
  },
  serverMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  roleBadge: {
    color: '#007AFF',
    fontSize: 12,
    backgroundColor: 'rgba(0,122,255,0.15)',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
    overflow: 'hidden',
  },
  serverId: {
    color: '#666',
    fontSize: 12,
  },
  serverTime: {
    color: '#666',
    fontSize: 12,
    marginTop: 4,
  },
  bindButton: {
    backgroundColor: '#007AFF',
    paddingVertical: 12,
    alignItems: 'center',
  },
  bindButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  requestsSection: {
    backgroundColor: '#333',
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: '#444',
  },
  requestsTitle: {
    color: '#ff9500',
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 8,
  },
  requestRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
  },
  requestUser: {
    color: '#ccc',
    fontSize: 14,
  },
  requestActions: {
    flexDirection: 'row',
    gap: 8,
  },
  approveBtn: {
    backgroundColor: '#34C759',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 6,
  },
  approveBtnText: {
    color: '#fff',
    fontSize: 13,
  },
  rejectBtn: {
    backgroundColor: '#ff4444',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 6,
  },
  rejectBtnText: {
    color: '#fff',
    fontSize: 13,
  },
  empty: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 40,
  },
  emptyText: {
    color: '#888',
    fontSize: 16,
    textAlign: 'center',
  },
  emptyHint: {
    color: '#555',
    fontSize: 13,
    textAlign: 'center',
    marginTop: 8,
  },
});
