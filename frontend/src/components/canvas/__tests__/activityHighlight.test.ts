import { describe, it, expect } from 'vitest'
import {
  ACTIVITY_WINDOW_MS,
  chatActivityKey,
  noteActivityKey,
  parseCreatedAt,
  isInActivityWindow,
  isInActivity,
  computeChatHighlightStyle,
  computeNoteHighlightStyle,
} from '../activityHighlight'

describe('chatActivityKey', () => {
  it('human → human:Name', () => {
    expect(chatActivityKey('human', 'Alice')).toBe('human:Alice')
  })
  it('ai → ai:Name', () => {
    expect(chatActivityKey('ai', 'Crew 1')).toBe('ai:Crew 1')
  })
  it('其他類型 → other:Name', () => {
    expect(chatActivityKey('system', 'Sys')).toBe('other:Sys')
  })
})

describe('noteActivityKey', () => {
  it('parses "Name(human)"', () => {
    expect(noteActivityKey('Alice(human)')).toBe('human:Alice')
  })
  it('parses "Name(ai)"', () => {
    expect(noteActivityKey('Crew 1(ai)')).toBe('ai:Crew 1')
  })
  it('與 chatActivityKey 對齊（同人）', () => {
    expect(noteActivityKey('Alice(human)')).toBe(chatActivityKey('human', 'Alice'))
  })
  it('未知 author → ai:?', () => {
    expect(noteActivityKey(null)).toBe('ai:?')
  })
})

describe('parseCreatedAt', () => {
  it('valid ISO → epoch ms', () => {
    const ms = parseCreatedAt('2026-05-19T08:00:00.000Z')
    expect(Number.isFinite(ms)).toBe(true)
    expect(new Date(ms).toISOString()).toBe('2026-05-19T08:00:00.000Z')
  })
  it('empty / missing → NaN', () => {
    expect(parseCreatedAt('')).toBeNaN()
    expect(parseCreatedAt(undefined)).toBeNaN()
    expect(parseCreatedAt(null)).toBeNaN()
  })
  it('garbage → NaN', () => {
    expect(parseCreatedAt('not-a-date')).toBeNaN()
  })
})

describe('isInActivityWindow', () => {
  const anchor = Date.parse('2026-05-19T08:00:00Z')
  it('差 0 秒 → true', () => {
    expect(isInActivityWindow(anchor, anchor)).toBe(true)
  })
  it('差 29 秒 → true', () => {
    expect(isInActivityWindow(anchor + 29_000, anchor)).toBe(true)
  })
  it('差 30 秒 → true（邊界 inclusive）', () => {
    expect(isInActivityWindow(anchor + 30_000, anchor)).toBe(true)
  })
  it('差 31 秒 → false', () => {
    expect(isInActivityWindow(anchor + 31_000, anchor)).toBe(false)
  })
  it('反向差 31 秒 → false', () => {
    expect(isInActivityWindow(anchor - 31_000, anchor)).toBe(false)
  })
  it('anchorMs NaN → 退化為 true（不限時間）', () => {
    expect(isInActivityWindow(anchor, NaN)).toBe(true)
  })
  it('otherMs NaN → 退化為 true', () => {
    expect(isInActivityWindow(NaN, anchor)).toBe(true)
  })
})

describe('isInActivity', () => {
  const anchorMs = Date.parse('2026-05-19T08:00:00Z')
  const anchor = { key: 'human:Alice', anchorMs, source: 'chat' as const }

  it('同 key + 時間窗內 → true', () => {
    expect(
      isInActivity({ key: 'human:Alice', otherMs: anchorMs + 10_000 }, anchor),
    ).toBe(true)
  })
  it('不同 key → 一律 false', () => {
    expect(
      isInActivity({ key: 'ai:Crew', otherMs: anchorMs }, anchor),
    ).toBe(false)
  })
  it('同 key 但時間差 > 30s → false', () => {
    expect(
      isInActivity(
        { key: 'human:Alice', otherMs: anchorMs + 60_000 },
        anchor,
      ),
    ).toBe(false)
  })
  it('同 key + 缺 created_at（NaN）→ 退化為 true（同作者全亮）', () => {
    expect(
      isInActivity({ key: 'human:Alice', otherMs: NaN }, anchor),
    ).toBe(true)
  })
})

describe('ACTIVITY_WINDOW_MS', () => {
  it('預設 30 秒', () => {
    expect(ACTIVITY_WINDOW_MS).toBe(30_000)
  })
})

describe('computeChatHighlightStyle', () => {
  const accent = '#BD6C48'
  const baseAnchor = {
    key: 'human:Alice',
    anchorMs: 1_000_000,
    source: 'chat' as const,
  }

  it('active = null → undefined（不疊樣式）', () => {
    expect(
      computeChatHighlightStyle({
        key: 'human:Alice',
        anchorMs: 1_000_000,
        active: null,
        accentColor: accent,
      }),
    ).toBeUndefined()
  })

  it('不同作者 → undefined', () => {
    expect(
      computeChatHighlightStyle({
        key: 'human:Bob',
        anchorMs: 1_000_000,
        active: baseAnchor,
        accentColor: accent,
      }),
    ).toBeUndefined()
  })

  it('同作者 + 30s 內 + 非來源 → 只有 box-shadow，無 outline', () => {
    const style = computeChatHighlightStyle({
      key: 'human:Alice',
      anchorMs: 1_010_000,
      active: baseAnchor,
      accentColor: accent,
    })
    expect(style).toBeDefined()
    expect(style?.boxShadow).toBe(`0 0 0 2px ${accent}`)
    expect(style?.outline).toBeUndefined()
    expect(style?.outlineOffset).toBeUndefined()
  })

  it('同作者 + 同 anchorMs + source=chat → 加 outline + offset 標記來源', () => {
    const style = computeChatHighlightStyle({
      key: 'human:Alice',
      anchorMs: 1_000_000,
      active: baseAnchor,
      accentColor: accent,
    })
    expect(style?.boxShadow).toBe(`0 0 0 2px ${accent}`)
    expect(style?.outline).toBe(`2px solid ${accent}`)
    expect(style?.outlineOffset).toBe('2px')
  })

  it('來源是 note（非 chat） → 不加 outline 即使 anchorMs 相同', () => {
    const noteAnchor = { ...baseAnchor, source: 'note' as const }
    const style = computeChatHighlightStyle({
      key: 'human:Alice',
      anchorMs: 1_000_000,
      active: noteAnchor,
      accentColor: accent,
    })
    expect(style?.boxShadow).toBe(`0 0 0 2px ${accent}`)
    expect(style?.outline).toBeUndefined()
  })

  it('時間差 > 30s → undefined', () => {
    expect(
      computeChatHighlightStyle({
        key: 'human:Alice',
        anchorMs: 1_000_000 + 31_000,
        active: baseAnchor,
        accentColor: accent,
      }),
    ).toBeUndefined()
  })

  it('CSS 值不含 rgb()+hex-alpha 串接（regression for commit 8a0fa5a）', () => {
    const style = computeChatHighlightStyle({
      key: 'human:Alice',
      anchorMs: 1_000_000,
      active: baseAnchor,
      accentColor: accent,
    })
    expect(style?.boxShadow).not.toMatch(/rgb\([^)]+\)[0-9a-f]{2}/i)
    expect(style?.outline).not.toMatch(/rgb\([^)]+\)[0-9a-f]{2}/i)
  })
})

describe('computeNoteHighlightStyle', () => {
  const accent = '#8B4B2A'
  const anchor = {
    key: 'human:Alice',
    anchorMs: 2_000_000,
    source: 'note' as const,
  }

  it('active = null → null', () => {
    expect(
      computeNoteHighlightStyle({
        noteKey: 'human:Alice',
        noteCreatedAtMs: 2_000_000,
        active: null,
        accentColor: accent,
        zoom: 1,
      }),
    ).toBeNull()
  })

  it('不同作者 → null', () => {
    expect(
      computeNoteHighlightStyle({
        noteKey: 'human:Bob',
        noteCreatedAtMs: 2_000_000,
        active: anchor,
        accentColor: accent,
        zoom: 1,
      }),
    ).toBeNull()
  })

  it('同作者 + 視窗內 + 非來源 → border 無 outline', () => {
    const style = computeNoteHighlightStyle({
      noteKey: 'human:Alice',
      noteCreatedAtMs: 2_010_000,
      active: anchor,
      accentColor: accent,
      zoom: 1,
    })
    expect(style?.border).toBe(`2px solid ${accent}`)
    expect(style?.outline).toBeUndefined()
  })

  it('同作者 + 同 anchorMs + source=note → border + outline', () => {
    const style = computeNoteHighlightStyle({
      noteKey: 'human:Alice',
      noteCreatedAtMs: 2_000_000,
      active: anchor,
      accentColor: accent,
      zoom: 1,
    })
    expect(style?.outline).toBe(`2px solid ${accent}`)
    expect(style?.outlineOffset).toBe('2px')
  })

  it('zoom 縮放 border 厚度 (Math.max(2, 2*zoom))', () => {
    const style = computeNoteHighlightStyle({
      noteKey: 'human:Alice',
      noteCreatedAtMs: 2_010_000,
      active: anchor,
      accentColor: accent,
      zoom: 2,
    })
    expect(style?.border).toBe(`4px solid ${accent}`)
  })

  it('zoom < 1 也至少 2px border', () => {
    const style = computeNoteHighlightStyle({
      noteKey: 'human:Alice',
      noteCreatedAtMs: 2_010_000,
      active: anchor,
      accentColor: accent,
      zoom: 0.5,
    })
    expect(style?.border).toBe(`2px solid ${accent}`)
  })

  it('時間差 > 30s → null', () => {
    expect(
      computeNoteHighlightStyle({
        noteKey: 'human:Alice',
        noteCreatedAtMs: 2_000_000 + 31_000,
        active: anchor,
        accentColor: accent,
        zoom: 1,
      }),
    ).toBeNull()
  })

  it('source=chat 時，note 即使同 anchorMs 也不算來源（不加 outline）', () => {
    const chatAnchor = { ...anchor, source: 'chat' as const }
    const style = computeNoteHighlightStyle({
      noteKey: 'human:Alice',
      noteCreatedAtMs: 2_000_000,
      active: chatAnchor,
      accentColor: accent,
      zoom: 1,
    })
    expect(style?.border).toBe(`2px solid ${accent}`)
    expect(style?.outline).toBeUndefined()
  })
})
