/**
 * useTimerTick — 計時器「每秒本地遞減」的單一計時源（spec 16 §5）。
 *
 * 必須在 workspace 樹中**只掛載一次**（WorkspacePage 本體），不可放進會被
 * 響應式分支（mobile `md:hidden` / desktop `hidden md:block`）重複渲染的元件。
 *
 * 背景：`TimerInline` 原本各自 `setInterval(tick,1000)`，而 Workspace 同時掛了
 * 手機與桌機兩個 `TimerInline`（Tailwind `hidden` 只切 CSS、React 不 unmount），
 * 導致共用 store 的 `tick()` 每秒被呼叫兩次、`used_seconds` 每秒 +2，再被 server
 * 快照覆蓋回真值 → 倒數「−2 再 +2」抖動。把計時集中於此即根除。
 */

import { useEffect } from 'react'
import { useTimerStore } from '../stores/timerStore'

export function useTimerTick(): void {
  const available = useTimerStore((s) => s.snapshot.available)
  const paused = useTimerStore((s) => s.snapshot.paused)
  const tick = useTimerStore((s) => s.tick)

  useEffect(() => {
    if (!available || paused) return
    const id = window.setInterval(() => tick(), 1000)
    return () => window.clearInterval(id)
  }, [available, paused, tick])
}
