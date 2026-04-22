import React, { useState, useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { ReviewInfo } from '../types';
import apiService from '../services/api';

interface ReviewCardProps {
  review: ReviewInfo;
  onResult: (message: string) => void;
}

export default function ReviewCard({ review, onResult }: ReviewCardProps) {
  const [status, setStatus] = useState<'pending' | 'approved' | 'rejected' | 'expired'>('pending');
  const [loading, setLoading] = useState(false);
  const [remaining, setRemaining] = useState(review.expires_in || 120);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const actionInProgress = useRef(false);

  useEffect(() => {
    if (status !== 'pending') return;

    timerRef.current = setInterval(() => {
      setRemaining(prev => {
        if (prev <= 1) {
          setStatus('expired');
          if (timerRef.current) clearInterval(timerRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [status]);

  const handleAction = async (action: 'approve' | 'reject') => {
    if (!review.pending_id || status !== 'pending') return;
    // 用ref防止双击，比state更快生效
    if (actionInProgress.current) return;
    actionInProgress.current = true;
    setLoading(true);

    const result = await apiService.confirmPendingCommand(review.pending_id, action);

    if (result.success && result.data) {
      setStatus(action === 'approve' ? 'approved' : 'rejected');
      onResult(result.data.message);
    } else {
      onResult(`${result.error}`);
      if (result.error === '确认请求已过期') {
        setStatus('expired');
      }
      actionInProgress.current = false;
    }
    setLoading(false);
  };

  const riskColor = review.risk_level === 'high' ? '#FF3B30' : '#FF9500';
  const isDisabled = status !== 'pending' || loading;

  return (
    <View style={[styles.card, { borderLeftColor: riskColor }]}>
      <Text style={styles.title}>
        {status === 'pending' ? '!! ' : status === 'approved' ? '' : status === 'rejected' ? '' : ''}
        {status === 'pending' ? '需要确认' :
         status === 'approved' ? '已确认执行' :
         status === 'rejected' ? '已取消' : '已过期'}
      </Text>

      <View style={styles.commandRow}>
        <Text style={styles.commandLabel}>命令:</Text>
        <Text style={styles.commandText}>{review.command}</Text>
      </View>

      <Text style={styles.reason}>{review.reason}</Text>

      {status === 'pending' && (
        <>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              style={[styles.button, styles.approveButton, isDisabled && styles.buttonDisabled]}
              onPress={() => handleAction('approve')}
              disabled={isDisabled}
            >
              <Text style={styles.buttonText}>
                {loading ? '...' : '确认执行'}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.button, styles.rejectButton, isDisabled && styles.buttonDisabled]}
              onPress={() => handleAction('reject')}
              disabled={isDisabled}
            >
              <Text style={styles.buttonText}>
                {loading ? '...' : '取消'}
              </Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.timer}>
            {remaining}秒内未确认将自动取消
          </Text>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#2a2a2a',
    borderRadius: 12,
    borderLeftWidth: 4,
    padding: 14,
    marginBottom: 12,
    maxWidth: '85%',
    alignSelf: 'flex-start',
  },
  title: {
    color: '#FF9500',
    fontSize: 15,
    fontWeight: '700',
    marginBottom: 8,
  },
  commandRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
  },
  commandLabel: {
    color: '#888',
    fontSize: 13,
    marginRight: 6,
  },
  commandText: {
    color: '#fff',
    fontSize: 14,
    fontFamily: 'monospace',
    flex: 1,
  },
  reason: {
    color: '#ccc',
    fontSize: 13,
    marginBottom: 10,
    lineHeight: 18,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 8,
  },
  button: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  approveButton: {
    backgroundColor: '#34C759',
  },
  rejectButton: {
    backgroundColor: '#555',
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  timer: {
    color: '#888',
    fontSize: 11,
    textAlign: 'center',
  },
});
