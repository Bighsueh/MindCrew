import { describe, it, expect } from 'vitest'
import { buildRecord } from '../useAnimatedYjsSync'

// buildRecord 把 sidecar 寫入 Yjs 的 raw shape 轉成 tldraw record。
// 重點守門：座標必須是有限數字，否則退回 fallback；但合法的 0 不可被誤判。
function rec(shape: Record<string, unknown>, idx = 0) {
  return buildRecord('note_abc', shape, idx) as unknown as {
    id: string
    type: string
    x: number
    y: number
    props: { text: string; color: string }
    meta: { kind: string; group_id: string; author: string }
  }
}

describe('buildRecord — 座標有限數驗證', () => {
  it('合法的 x=0 / y=0 必須保留（不被 falsy fallback 換掉）', () => {
    const r = rec({ x: 0, y: 0 }, 5)
    expect(r.x).toBe(0)
    expect(r.y).toBe(0)
  })

  it('正常有限座標原樣帶過', () => {
    const r = rec({ x: 939.69, y: 786.81 })
    expect(r.x).toBeCloseTo(939.69)
    expect(r.y).toBeCloseTo(786.81)
  })

  it('NaN 座標 → 退回 fallback（不把 NaN 餵進 store）', () => {
    const r = rec({ x: NaN, y: NaN }, 0)
    expect(Number.isFinite(r.x)).toBe(true)
    expect(Number.isFinite(r.y)).toBe(true)
    expect(r.x).toBe(100)
    expect(r.y).toBe(100)
  })

  it('Infinity 座標 → 退回 fallback', () => {
    const r = rec({ x: Infinity, y: -Infinity }, 1)
    expect(r.x).toBe(130)
    expect(r.y).toBe(130)
  })

  it('缺失 / 非數字座標 → 退回 fallback（含字串、null、undefined）', () => {
    expect(Number.isFinite(rec({}, 0).x)).toBe(true)
    expect(rec({ x: '100' as unknown as number }, 0).x).toBe(100)
    expect(rec({ x: null as unknown as number }, 2).x).toBe(160)
  })
})

describe('buildRecord — 其餘欄位', () => {
  it('id 自動補 shape: 前綴', () => {
    expect(rec({}).id).toBe('shape:note_abc')
  })

  it('color 映射（pink → light-red、未知 → yellow）', () => {
    expect(rec({ color: 'pink' }).props.color).toBe('light-red')
    expect(rec({ color: 'not-a-color' }).props.color).toBe('yellow')
  })

  it('content 缺失 → 空字串、Spec 27 的 kind/group_id 帶進 meta', () => {
    const r = rec({ kind: 'label', group_id: '搬運風險' })
    expect(r.props.text).toBe('')
    expect(r.meta.kind).toBe('label')
    expect(r.meta.group_id).toBe('搬運風險')
  })
})
