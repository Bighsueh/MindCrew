import { describe, it, expect, beforeEach } from 'vitest'
import { useTimerStore, type TimerStateSnapshot } from '../timerStore'

// Bug A 守衛（spec 16 §5/§4.18）：server 快照覆蓋時，同一 sub_phase 內小幅往回
// 視為對齊抖動、壓住不讓倒數回跳；換 sub_phase／pause 翻轉／大幅漂移則完整採用。
function seed(partial: Partial<TimerStateSnapshot> = {}): void {
  useTimerStore.setState({
    snapshot: {
      current_sub_phase: '0.0a',
      current_sub_phase_label: '暖場',
      budget_seconds: 300,
      used_seconds: 10,
      paused: false,
      used_pct: (10 / 300) * 100,
      available: true,
      sub_phase_budget_seconds: 300,
      sub_phase_used_seconds: 10,
      warmup_goal: 8,
      warmup_soft_seconds: 180,
      ...partial,
    },
  })
}

describe('timerStore.setSnapshot 單調對齊守衛', () => {
  beforeEach(() => seed())

  it('同 sub_phase 內小幅往回（≤5s）被壓住、倒數不回跳', () => {
    useTimerStore.getState().setSnapshot({ used_seconds: 8 })
    expect(useTimerStore.getState().snapshot.used_seconds).toBe(10)
    // 別名同步壓住，欄位不打架
    expect(useTimerStore.getState().snapshot.sub_phase_used_seconds).toBe(10)
  })

  it('往前校正照常採用', () => {
    useTimerStore.getState().setSnapshot({ used_seconds: 13 })
    expect(useTimerStore.getState().snapshot.used_seconds).toBe(13)
  })

  it('換 sub_phase 時完整採用 server 值（允許歸零）', () => {
    useTimerStore
      .getState()
      .setSnapshot({ current_sub_phase: '1.1a', used_seconds: 2 })
    expect(useTimerStore.getState().snapshot.used_seconds).toBe(2)
  })

  it('大幅往回（>5s）視為真實漂移、採用 server 值', () => {
    useTimerStore.getState().setSnapshot({ used_seconds: 3 })
    expect(useTimerStore.getState().snapshot.used_seconds).toBe(3)
  })

  it('pause 翻轉時重置、採用 server 值', () => {
    useTimerStore.getState().setSnapshot({ paused: true, used_seconds: 8 })
    expect(useTimerStore.getState().snapshot.used_seconds).toBe(8)
  })
})

describe('timerStore.tick 單一計時源', () => {
  beforeEach(() => seed())

  it('每次 tick 只 +1 秒（單一計時源契約；雙計時會 +2）', () => {
    useTimerStore.getState().tick()
    expect(useTimerStore.getState().snapshot.used_seconds).toBe(11)
  })

  it('paused 時 tick 不前進', () => {
    seed({ paused: true })
    useTimerStore.getState().tick()
    expect(useTimerStore.getState().snapshot.used_seconds).toBe(10)
  })
})
