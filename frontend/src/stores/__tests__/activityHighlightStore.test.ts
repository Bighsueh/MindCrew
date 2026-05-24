import { describe, it, expect, beforeEach } from 'vitest'
import { useActivityHighlightStore, selectActiveAnchor } from '../activityHighlightStore'
import type { ActivityAnchor } from '../../components/canvas/activityHighlight'

const A: ActivityAnchor = { key: 'human:Alice', anchorMs: 1_000, source: 'chat' }
const B: ActivityAnchor = { key: 'ai:Crew 1', anchorMs: 2_000, source: 'note' }

describe('activityHighlightStore', () => {
  beforeEach(() => {
    useActivityHighlightStore.getState().clearAll()
  })

  it('setHover / clearHover 切換 hover 狀態', () => {
    const s = useActivityHighlightStore
    s.getState().setHover(A)
    expect(s.getState().hover).toEqual(A)
    s.getState().clearHover()
    expect(s.getState().hover).toBeNull()
  })

  it('setHover 相同 anchor 不應觸發新引用（避免重渲染）', () => {
    const s = useActivityHighlightStore
    s.getState().setHover(A)
    const ref1 = s.getState()
    s.getState().setHover({ ...A })
    const ref2 = s.getState()
    // state 物件本身不變（淺比較會相等）
    expect(ref1).toBe(ref2)
  })

  it('togglePinned 同對象再次 → 清除', () => {
    const s = useActivityHighlightStore
    s.getState().togglePinned(A)
    expect(s.getState().pinned).toEqual(A)
    s.getState().togglePinned({ ...A })
    expect(s.getState().pinned).toBeNull()
  })

  it('togglePinned 不同對象 → 覆蓋', () => {
    const s = useActivityHighlightStore
    s.getState().togglePinned(A)
    s.getState().togglePinned(B)
    expect(s.getState().pinned).toEqual(B)
  })

  it('pinned 優先於 hover', () => {
    const s = useActivityHighlightStore
    s.getState().setHover(A)
    s.getState().togglePinned(B)
    expect(selectActiveAnchor(s.getState())).toEqual(B)
  })

  it('沒有 pinned 時 active = hover', () => {
    const s = useActivityHighlightStore
    s.getState().setHover(A)
    expect(selectActiveAnchor(s.getState())).toEqual(A)
  })

  it('clearAll 一次清乾淨', () => {
    const s = useActivityHighlightStore
    s.getState().setHover(A)
    s.getState().togglePinned(B)
    s.getState().clearAll()
    expect(s.getState().hover).toBeNull()
    expect(s.getState().pinned).toBeNull()
  })
})
