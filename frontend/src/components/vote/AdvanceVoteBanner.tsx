/**
 * AdvanceVoteBanner — Spec 14 N2.
 *
 * 全頂部 banner，crew 推進投票進行時顯示倒數 + 即時票數 + 老師取消按鈕。
 */

import { useEffect, useState } from 'react'
import api from '@/services/api'

export type VoteChoice = 'approve' | 'reject' | 'abstain'

export interface AdvanceVoteSession {
  session_id: string
  sub_phase: string
  trigger_reason: string
  expires_at: number // unix seconds
  voters: Array<{
    voter_id: string
    voter_name: string
    choice: VoteChoice
  }>
}

interface AdvanceVoteBannerProps {
  projectId: string
  isTeacher: boolean
  currentUserId: string
  session: AdvanceVoteSession | null
}

export function AdvanceVoteBanner({
  projectId,
  isTeacher,
  currentUserId,
  session,
}: AdvanceVoteBannerProps) {
  const [now, setNow] = useState(() => Date.now() / 1000)
  const [working, setWorking] = useState(false)

  useEffect(() => {
    if (!session) return
    const id = window.setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => window.clearInterval(id)
  }, [session])

  if (!session) return null

  const secondsRemaining = Math.max(0, Math.floor(session.expires_at - now))
  const approve = session.voters.filter((v) => v.choice === 'approve').length
  const reject = session.voters.filter((v) => v.choice === 'reject').length
  const abstain = session.voters.filter((v) => v.choice === 'abstain').length
  const myVote = session.voters.find((v) => v.voter_id === currentUserId)?.choice

  const cast = async (choice: VoteChoice) => {
    if (working) return
    setWorking(true)
    try {
      await api.post(`/projects/${projectId}/advance-vote/cast`, { choice })
    } finally {
      setWorking(false)
    }
  }

  const cancel = async () => {
    if (!isTeacher || working) return
    setWorking(true)
    try {
      await api.post(`/projects/${projectId}/advance-vote/cancel`)
    } finally {
      setWorking(false)
    }
  }

  return (
    <div
      role="alertdialog"
      aria-live="assertive"
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        background: '#fef3c7',
        borderBottom: '2px solid #d97706',
        padding: '10px 16px',
        zIndex: 80,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        animation: 'slide-down-200 200ms ease-out',
      }}
    >
      <div style={{ fontWeight: 600, color: '#92400e' }}>
        🗳 推進投票（{session.sub_phase}）
      </div>
      <div style={{ fontSize: 13, color: '#7c2d12' }}>
        {session.trigger_reason}
      </div>
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 12, alignItems: 'center' }}>
        <span style={{ fontSize: 13, fontVariantNumeric: 'tabular-nums' }}>
          ⏳ {secondsRemaining}s
        </span>
        <span style={{ fontSize: 13 }}>
          同意 <strong style={{ color: '#16a34a' }}>{approve}</strong> · 反對{' '}
          <strong style={{ color: '#dc2626' }}>{reject}</strong> · 棄權 {abstain}
        </span>
        {!myVote && (
          <>
            <button onClick={() => cast('approve')} disabled={working} style={voteBtnStyle('approve')}>
              同意
            </button>
            <button onClick={() => cast('reject')} disabled={working} style={voteBtnStyle('reject')}>
              反對
            </button>
            <button onClick={() => cast('abstain')} disabled={working} style={voteBtnStyle('abstain')}>
              棄權
            </button>
          </>
        )}
        {myVote && (
          <span style={{ fontSize: 13, color: '#6b7280' }}>
            已投：{myVote === 'approve' ? '同意' : myVote === 'reject' ? '反對' : '棄權'}
          </span>
        )}
        {isTeacher && (
          <button onClick={cancel} disabled={working} style={voteBtnStyle('cancel')}>
            取消
          </button>
        )}
      </div>
    </div>
  )
}

function voteBtnStyle(kind: 'approve' | 'reject' | 'abstain' | 'cancel'): React.CSSProperties {
  const map = {
    approve: { bg: '#16a34a', fg: '#fff' },
    reject: { bg: '#dc2626', fg: '#fff' },
    abstain: { bg: '#6b7280', fg: '#fff' },
    cancel: { bg: 'transparent', fg: '#7c2d12', border: '1px solid #d97706' },
  }
  const c = map[kind]
  return {
    background: c.bg,
    color: c.fg,
    border: (c as { border?: string }).border ?? 'none',
    padding: '6px 14px',
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    minHeight: 36,
  }
}
