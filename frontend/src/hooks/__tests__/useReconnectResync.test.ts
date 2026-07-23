import { describe, it, expect, beforeEach, vi } from 'vitest'

// api.ts reads localStorage at import time — stub before importing anything that pulls it in.
vi.hoisted(() => {
  const mem: Record<string, string> = {}
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(globalThis as any).localStorage = {
    getItem: (k: string) => (k in mem ? mem[k] : null),
    setItem: (k: string, v: string) => {
      mem[k] = v
    },
    removeItem: (k: string) => {
      delete mem[k]
    },
    clear: () => {
      for (const k of Object.keys(mem)) delete mem[k]
    },
    key: () => null,
    length: 0,
  }
})

vi.mock('../../services/projectService', () => ({
  getStage: vi.fn(),
  getSeats: vi.fn(),
  getMessages: vi.fn(),
  getHumanGate: vi.fn(),
}))

import { resyncCriticalSurface } from '../useReconnectResync'
import {
  getStage,
  getSeats,
  getMessages,
  getHumanGate,
} from '../../services/projectService'
import { useStageStore } from '../../stores/stageStore'
import { useSeatStore } from '../../stores/seatStore'
import { useHumanGateStore } from '../../stores/humanGateStore'

const mGetStage = vi.mocked(getStage)
const mGetSeats = vi.mocked(getSeats)
const mGetMessages = vi.mocked(getMessages)
const mGetHumanGate = vi.mocked(getHumanGate)

beforeEach(() => {
  vi.clearAllMocks()
  mGetStage.mockResolvedValue({
    current_stage: 'discover',
    current_micro_phase: '1.2',
    started_at: '',
    duration_seconds: 0,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any)
  mGetSeats.mockResolvedValue([])
  mGetMessages.mockResolvedValue({ messages: [], has_more: false })
  mGetHumanGate.mockResolvedValue({ user_task: null, waiting: null, sub_phase: '1.2' })
  useStageStore.setState({ currentStage: 'warmup', currentMicroPhase: null })
  useSeatStore.setState({ seats: [] })
  useHumanGateStore.setState({ waiting: null, task: null, bounce: null })
})

describe('resyncCriticalSurface', () => {
  it('全量重抓並把 stage 對齊到 server truth', async () => {
    await resyncCriticalSurface({ projectId: 'p1', currentUserId: 'u1' })
    expect(mGetStage).toHaveBeenCalledWith('p1')
    expect(mGetSeats).toHaveBeenCalledWith('p1')
    expect(useStageStore.getState().currentStage).toBe('discover')
    expect(useStageStore.getState().currentMicroPhase).toBe('1.2')
  })

  it('有 currentUserId → 連 personal 聊天一起重抓', async () => {
    await resyncCriticalSurface({ projectId: 'p1', currentUserId: 'u1' })
    const chatIds = mGetMessages.mock.calls.map((c) => c[1]?.chatId)
    expect(chatIds).toContain('p1:group')
    expect(chatIds).toContain('p1:personal:u1')
  })

  it('無 currentUserId → 不抓 personal（避免拿到別人的訊息）', async () => {
    await resyncCriticalSurface({ projectId: 'p1' })
    const chatIds = mGetMessages.mock.calls.map((c) => c[1]?.chatId)
    expect(chatIds).toContain('p1:group')
    expect(chatIds.some((id) => String(id).includes(':personal:'))).toBe(false)
  })

  it('allSettled：某面向失敗不阻斷其餘（seats 失敗、stage 仍收斂）', async () => {
    mGetSeats.mockRejectedValueOnce(new Error('boom'))
    await resyncCriticalSurface({ projectId: 'p1', currentUserId: 'u1' })
    expect(useStageStore.getState().currentStage).toBe('discover')
  })

  // Phase 42 補正 R4（A-P1）：human-gate 水合。
  it('human-gate 快照 → 重建 TaskBanner 與等待列', async () => {
    mGetHumanGate.mockResolvedValueOnce({
      user_task: { task_text: '貼一張便條', sub_phase: '1.2', action_kind: 'note' },
      waiting: {
        sub_phase: '1.2',
        round: 2,
        required: { note: true, chat: false, move: false, confirm: false, mode: 'any' },
      },
      sub_phase: '1.2',
    })
    await resyncCriticalSurface({ projectId: 'p1', currentUserId: 'u1' })
    const gate = useHumanGateStore.getState()
    expect(gate.task?.taskText).toBe('貼一張便條')
    expect(gate.waiting?.round).toBe(2)
  })

  it('human-gate 快照說沒在等 → 清殘留等待列（斷線空窗已解鎖自癒）', async () => {
    useHumanGateStore.setState({
      waiting: {
        subPhase: '1.2',
        round: 1,
        required: { note: true, chat: false, move: false, confirm: false, mode: 'any' },
        targetUserId: 'u1',
      },
      task: null,
      bounce: null,
    })
    await resyncCriticalSurface({ projectId: 'p1', currentUserId: 'u1' })
    expect(useHumanGateStore.getState().waiting).toBeNull()
  })
})
