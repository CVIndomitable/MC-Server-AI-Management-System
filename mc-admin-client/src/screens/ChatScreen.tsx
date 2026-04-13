import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  TextInput,
  TouchableOpacity,
  FlatList,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Switch,
} from 'react-native';
import { useAppStore } from '../services/store';
import { ChatMessage, ModelTier } from '../types';

const MODEL_OPTIONS: { label: string; value: ModelTier | undefined; desc: string }[] = [
  { label: '自动', value: undefined, desc: '系统自动选择' },
  { label: '极速', value: 'flash', desc: '简单任务' },
  { label: '标准', value: 'standard', desc: '日常使用' },
  { label: '专业', value: 'pro', desc: '复杂分析' },
];

export default function ChatScreen() {
  const [inputText, setInputText] = useState('');
  const [showModelPicker, setShowModelPicker] = useState(false);
  const {
    chatMessages, sendMessage, isLoading,
    queryOnlyMode, toggleQueryOnlyMode,
    modelTier, setModelTier,
  } = useAppStore();
  const flatListRef = useRef<FlatList>(null);

  useEffect(() => {
    if (chatMessages.length > 0) {
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 100);
    }
  }, [chatMessages]);

  const handleSend = async () => {
    if (!inputText.trim() || isLoading) return;

    const message = inputText.trim();
    setInputText('');
    await sendMessage(message);
  };

  const currentModelLabel = MODEL_OPTIONS.find(m => m.value === modelTier)?.label || '自动';

  const renderMessage = ({ item }: { item: ChatMessage }) => (
    <View
      style={[
        styles.messageBubble,
        item.role === 'user' ? styles.userBubble : styles.assistantBubble,
      ]}
    >
      <Text style={styles.messageText}>{item.content}</Text>
      <Text style={styles.timestamp}>
        {new Date(item.timestamp).toLocaleTimeString('zh-CN', {
          hour: '2-digit',
          minute: '2-digit',
        })}
      </Text>
    </View>
  );

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={90}
    >
      {/* 顶部控制栏 */}
      <View style={styles.modeBar}>
        <View style={styles.modeLeft}>
          <Text style={styles.modeLabel}>
            {queryOnlyMode ? '仅查询' : '正常'}
          </Text>
          <Switch
            value={queryOnlyMode}
            onValueChange={toggleQueryOnlyMode}
            trackColor={{ false: '#555', true: '#FF9500' }}
            thumbColor={queryOnlyMode ? '#fff' : '#ccc'}
          />
        </View>
        <TouchableOpacity
          style={styles.modelButton}
          onPress={() => setShowModelPicker(!showModelPicker)}
        >
          <Text style={styles.modelButtonText}>{currentModelLabel}</Text>
        </TouchableOpacity>
      </View>

      {/* 模型选择器 */}
      {showModelPicker && (
        <View style={styles.modelPicker}>
          {MODEL_OPTIONS.map((option) => (
            <TouchableOpacity
              key={option.label}
              style={[
                styles.modelOption,
                modelTier === option.value && styles.modelOptionActive,
              ]}
              onPress={() => {
                setModelTier(option.value);
                setShowModelPicker(false);
              }}
            >
              <Text style={[
                styles.modelOptionLabel,
                modelTier === option.value && styles.modelOptionLabelActive,
              ]}>
                {option.label}
              </Text>
              <Text style={styles.modelOptionDesc}>{option.desc}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      <FlatList
        ref={flatListRef}
        data={chatMessages}
        renderItem={renderMessage}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.messageList}
        inverted={false}
      />

      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          value={inputText}
          onChangeText={setInputText}
          placeholder="输入消息..."
          placeholderTextColor="#888"
          multiline
          maxLength={500}
          editable={!isLoading}
        />
        <TouchableOpacity
          style={[styles.sendButton, isLoading && styles.sendButtonDisabled]}
          onPress={handleSend}
          disabled={isLoading || !inputText.trim()}
        >
          <Text style={styles.sendButtonText}>
            {isLoading ? '...' : '发送'}
          </Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a1a',
  },
  modeBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: '#2a2a2a',
    borderBottomWidth: 1,
    borderBottomColor: '#333',
  },
  modeLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  modeLabel: {
    color: '#ccc',
    fontSize: 13,
  },
  modelButton: {
    backgroundColor: '#3a3a3a',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 14,
  },
  modelButtonText: {
    color: '#007AFF',
    fontSize: 13,
    fontWeight: '600',
  },
  modelPicker: {
    flexDirection: 'row',
    backgroundColor: '#2a2a2a',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#333',
    gap: 8,
  },
  modelOption: {
    flex: 1,
    backgroundColor: '#3a3a3a',
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 6,
    alignItems: 'center',
  },
  modelOptionActive: {
    backgroundColor: '#007AFF',
  },
  modelOptionLabel: {
    color: '#ccc',
    fontSize: 13,
    fontWeight: '600',
  },
  modelOptionLabelActive: {
    color: '#fff',
  },
  modelOptionDesc: {
    color: '#888',
    fontSize: 10,
    marginTop: 2,
  },
  messageList: {
    padding: 16,
    flexGrow: 1,
  },
  messageBubble: {
    maxWidth: '80%',
    padding: 12,
    borderRadius: 16,
    marginBottom: 12,
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: '#007AFF',
  },
  assistantBubble: {
    alignSelf: 'flex-start',
    backgroundColor: '#2a2a2a',
  },
  messageText: {
    color: '#fff',
    fontSize: 16,
    lineHeight: 22,
  },
  timestamp: {
    color: '#aaa',
    fontSize: 11,
    marginTop: 4,
  },
  inputContainer: {
    flexDirection: 'row',
    padding: 12,
    backgroundColor: '#2a2a2a',
    borderTopWidth: 1,
    borderTopColor: '#333',
  },
  input: {
    flex: 1,
    backgroundColor: '#1a1a1a',
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
    color: '#fff',
    fontSize: 16,
    maxHeight: 100,
  },
  sendButton: {
    marginLeft: 8,
    backgroundColor: '#007AFF',
    borderRadius: 20,
    paddingHorizontal: 20,
    justifyContent: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: '#555',
  },
  sendButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
