/**
 * TimerBadge — Spec 15 §6.1.
 *
 * 畫布頂部中央 floating badge，所有人可見。每秒本地遞減。
 */

import { useEffect } from 'react'
import {
  formatBudget,
  formatRemaining,
  getPressureLabel,
  getPressureLevel,
  useTimerStore,
  type PressureLevel,
} from '@/stores/timerStore'

interface ColorPalette {
  bg: string
  fg: string
  bar: string
}

// specs/16-timer-system.md §6.5.3：五階顏色對應 PressureLevel
// （tight / critical 在容器加 pulse 動畫，讓人類旁觀者也感受到壓力）。
const PRESSURE_PALETTE: Record<PressureLevel, ColorPalette> = {
  calm: { bg: '#dcfce7', fg: '#166534', bar: '#16a34a' },
  halfway: { bg: '#fef3c7', fg: '#92400e', bar: '#d97706' },
  two_thirds: { bg: '#ffedd5', fg: '#9a3412', bar: '#ea580c' },
  tight: { bg: '#fee2e2', fg: '#991b1b', bar: '#dc2626' },
  critical: { bg: '#fecaca', fg: '#7f1d1d', bar: '#b91c1c' },
}

export function TimerBadge() {
  const snapshot = useTimerStore((s) => s.snapshot)
  const tick = useTimerStore((s) => s.tick)

  useEffect(() => {
    if (!snapshot.available || snapshot.paused) return
    const id = window.setInterval(() => tick(), 1000)
    return () => window.clearInterval(id)
  }, [snapshot.available, snapshot.paused, tick])

  if (!snapshot.available || !snapshot.current_sub_phase) return null

  const pressure = getPressureLevel(snapshot.used_pct)
  const c = PRESSURE_PALETTE[pressure]
  const pct = Math.min(snapshot.used_pct, 100)
  const isOvertime = snapshot.used_pct >= 100
  const shouldPulse = isOvertime || pressure === 'critical' || pressure === 'tight'

  return (
    <div
      role="timer"
      aria-live="off"
      style={{
        position: 'absolute',
        top: 8,
        left: '50%',
        transform: 'translateX(-50%)',
        background: c.bg,
        color: c.fg,
        border: `2px solid ${c.bar}`,
        borderRadius: 10,
        padding: '8px 14px',
        minHeight: 56,
        minWidth: 280,
        zIndex: 60,
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
        fontWeight: 600,
        fontSize: 14,
        animation: shouldPulse ? 'timer-flash 1s linear infinite' : undefined,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span>{snapshot.paused ? '⏸' : '⏱'}</span>
        <span>{snapshot.current_sub_phase}</span>
        <span
          style={{
            fontSize: 11,
            padding: '1px 6px',
            borderRadius: 4,
            background: c.bar,
            color: '#fff',
            opacity: 0.85,
          }}
          aria-label="time-pressure-level"
        >
          {getPressureLabel(pressure)}
        </span>
        <span style={{ marginLeft: 'auto', fontVariantNumeric: 'tabular-nums' }}>
          剩 {formatRemaining(snapshot.budget_seconds, snapshot.used_seconds)} /{' '}
          {formatBudget(snapshot.budget_seconds)}
        </span>
      </div>
      <div
        style={{
          width: '100%',
          height: 6,
          background: 'rgba(0,0,0,0.08)',
          borderRadius: 3,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: c.bar,
            transition: 'width 0.5s linear',
          }}
        />
      </div>
    </div>
  )
}
