/**
 * TimerControlPanel — Spec 15 §6.2.
 *
 * 老師限定，畫布右下角折疊式 FAB。
 */

import { useState } from 'react'
import api from '@/services/api'
import { useTimerStore } from '@/stores/timerStore'

interface TimerControlPanelProps {
  projectId: string
  isTeacher: boolean
}

export function TimerControlPanel({ projectId, isTeacher }: TimerControlPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const [working, setWorking] = useState<string | null>(null)
  const snapshot = useTimerStore((s) => s.snapshot)
  const setSnapshot = useTimerStore((s) => s.setSnapshot)

  if (!isTeacher || !snapshot.available) return null

  const handle = async (op: 'pause' | 'resume' | 'extend') => {
    if (working) return
    setWorking(op)
    try {
      if (op === 'extend') {
        await api.post(`/projects/${projectId}/timer/extend`, {
          additional_minutes: 5,
        })
      } else {
        const r = await api.post<{ state?: { paused_at?: string } }>(
          `/projects/${projectId}/timer/${op}`,
        )
        setSnapshot({ paused: r.data.state?.paused_at != null })
      }
    } finally {
      setWorking(null)
    }
  }

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        aria-label="開啟 timer 控制"
        style={fabStyle}
      >
        ⏱
      </button>
    )
  }

  return (
    <div style={panelStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontWeight: 600, fontSize: 13 }}>Timer 控制</span>
        <button onClick={() => setExpanded(false)} aria-label="關閉" style={closeBtnStyle}>
          ×
        </button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <button
          onClick={() => handle(snapshot.paused ? 'resume' : 'pause')}
          disabled={working !== null}
          style={btnStyle}
        >
          {snapshot.paused ? '▶ 繼續' : '⏸ 暫停'}
        </button>
        <button
          onClick={() => handle('extend')}
          disabled={working !== null}
          style={btnStyle}
        >
          ➕ +5 分鐘
        </button>
      </div>
    </div>
  )
}

const fabStyle: React.CSSProperties = {
  position: 'absolute',
  bottom: 16,
  right: 16,
  width: 56,
  height: 56,
  borderRadius: 28,
  background: '#1f2937',
  color: 'white',
  border: 'none',
  fontSize: 20,
  cursor: 'pointer',
  boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
  zIndex: 60,
}

const panelStyle: React.CSSProperties = {
  position: 'absolute',
  bottom: 16,
  right: 16,
  width: 200,
  background: 'white',
  borderRadius: 10,
  padding: 12,
  boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
  zIndex: 60,
}

const btnStyle: React.CSSProperties = {
  padding: '8px 12px',
  border: '1px solid #d1d5db',
  borderRadius: 6,
  background: 'white',
  cursor: 'pointer',
  fontSize: 13,
  minHeight: 36,
  textAlign: 'left',
}

const closeBtnStyle: React.CSSProperties = {
  background: 'transparent',
  border: 'none',
  fontSize: 18,
  cursor: 'pointer',
  padding: 0,
  width: 24,
  height: 24,
}
