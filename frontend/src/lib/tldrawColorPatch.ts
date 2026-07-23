/**
 * MindCrew 便條紙色票 — 初始化一次性覆寫 tldraw DefaultColorThemePalette.
 *
 * tldraw 2.4 沒有提供 API 直接替換 note.fill；
 * 官方建議的唯一方式是在掛載前修改 DefaultColorThemePalette 這個模組層級常數。
 * 此操作在應用程式啟動時執行一次、早於任何 React 渲染，不影響響應式資料流。
 */
import { DefaultColorThemePalette } from '@tldraw/tlschema'

interface NoteTheme {
  fill: string
  text: string
}

const LIGHT_OVERRIDES: Record<string, NoteTheme> = {
  yellow: { fill: '#F8DC98', text: '#000000' },
  orange: { fill: '#F4C59A', text: '#000000' },
  green:  { fill: '#CCDC9A', text: '#000000' },
  blue:   { fill: '#BBD0CC', text: '#000000' },
  violet: { fill: '#F0C3D8', text: '#000000' },
  red:    { fill: '#F2DED2', text: '#000000' },
}

// tldraw 升版後 lightMode 多了 background/id/solid/text 等非色票欄位，與索引簽名
// 不再重疊 → 需先過 unknown（行為不變，僅型別斷言收斂）。
const palette = DefaultColorThemePalette.lightMode as unknown as Record<
  string,
  { note: NoteTheme }
>
for (const [token, noteTheme] of Object.entries(LIGHT_OVERRIDES)) {
  if (palette[token]?.note) {
    palette[token].note = noteTheme
  }
}
