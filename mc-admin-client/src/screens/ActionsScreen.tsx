import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  TextInput,
  Modal,
} from 'react-native';
import { useAppStore } from '../services/store';
import apiService from '../services/api';

interface QuickAction {
  id: string;
  title: string;
  icon: string;
  action: string;
  needsInput?: boolean;
  confirmMessage?: string;
  color: string;
}

const QUICK_ACTIONS: QuickAction[] = [
  {
    id: 'restart',
    title: '重启服务器',
    icon: '🔄',
    action: 'restart',
    confirmMessage: '确定要重启服务器吗？',
    color: '#FF9800',
  },
  {
    id: 'backup',
    title: '立即备份',
    icon: '💾',
    action: 'backup',
    color: '#4CAF50',
  },
  {
    id: 'announce',
    title: '发送公告',
    icon: '📢',
    action: 'announce',
    needsInput: true,
    color: '#2196F3',
  },
  {
    id: 'whitelist',
    title: '白名单管理',
    icon: '📋',
    action: 'whitelist',
    needsInput: true,
    color: '#9C27B0',
  },
  {
    id: 'stop',
    title: '停止服务器',
    icon: '⏹️',
    action: 'stop',
    confirmMessage: '确定要停止服务器吗？这将断开所有玩家连接。',
    color: '#F44336',
  },
  {
    id: 'save',
    title: '保存世界',
    icon: '💿',
    action: 'save',
    color: '#00BCD4',
  },
];

export default function ActionsScreen() {
  const { serverId } = useAppStore();
  const [modalVisible, setModalVisible] = useState(false);
  const [selectedAction, setSelectedAction] = useState<QuickAction | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);

  const handleActionPress = (action: QuickAction) => {
    if (action.needsInput) {
      setSelectedAction(action);
      setInputValue('');
      setModalVisible(true);
    } else if (action.confirmMessage) {
      Alert.alert('确认操作', action.confirmMessage, [
        { text: '取消', style: 'cancel' },
        { text: '确定', onPress: () => executeAction(action) },
      ]);
    } else {
      executeAction(action);
    }
  };

  const executeAction = async (action: QuickAction, params?: any) => {
    setIsExecuting(true);

    const result = await apiService.executeQuickAction(serverId, action.action, params);

    setIsExecuting(false);

    if (result.success) {
      Alert.alert('成功', `${action.title}执行成功`);
    } else {
      Alert.alert('失败', result.error || '操作失败');
    }
  };

  const handleModalConfirm = () => {
    if (!selectedAction) return;

    let params: any = {};

    if (selectedAction.id === 'announce') {
      params = { message: inputValue };
    } else if (selectedAction.id === 'whitelist') {
      params = { player: inputValue };
    }

    setModalVisible(false);
    executeAction(selectedAction, params);
  };

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.header}>快捷操作</Text>

      <View style={styles.grid}>
        {QUICK_ACTIONS.map((action) => (
          <TouchableOpacity
            key={action.id}
            style={[styles.actionButton, { borderColor: action.color }]}
            onPress={() => handleActionPress(action)}
            disabled={isExecuting}
          >
            <Text style={styles.actionIcon}>{action.icon}</Text>
            <Text style={styles.actionTitle}>{action.title}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* 输入模态框 */}
      <Modal
        visible={modalVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>{selectedAction?.title}</Text>

            <TextInput
              style={styles.modalInput}
              value={inputValue}
              onChangeText={setInputValue}
              placeholder={
                selectedAction?.id === 'announce'
                  ? '输入公告内容...'
                  : '输入玩家名称...'
              }
              placeholderTextColor="#888"
              multiline={selectedAction?.id === 'announce'}
            />

            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={[styles.modalButton, styles.cancelButton]}
                onPress={() => setModalVisible(false)}
              >
                <Text style={styles.buttonText}>取消</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.modalButton, styles.confirmButton]}
                onPress={handleModalConfirm}
                disabled={!inputValue.trim()}
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
  header: {
    color: '#fff',
    fontSize: 24,
    fontWeight: 'bold',
    margin: 16,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 8,
  },
  actionButton: {
    width: '45%',
    aspectRatio: 1,
    margin: '2.5%',
    backgroundColor: '#2a2a2a',
    borderRadius: 16,
    borderWidth: 2,
    justifyContent: 'center',
    alignItems: 'center',
  },
  actionIcon: {
    fontSize: 48,
    marginBottom: 8,
  },
  actionTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    textAlign: 'center',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContent: {
    width: '80%',
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
    marginBottom: 20,
    minHeight: 50,
  },
  modalButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
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
