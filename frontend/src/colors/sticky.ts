/**
 * Phase 22：席位識別色（tldraw 8 色 token → CSS）
 *
 * 與後端 `app/seats/colors.py::STICKY_COLOR_POOL` 對齊。
 * tldraw sticky note 預設色彩較淺，這裡為 chat bubble + 作者 dot 各自挑相應色。
 */

export type StickyColorToken =
  | 'yellow'
  | 'orange'
  | 'green'
  | 'blue'
  | 'violet'
  | 'red'
  | 'light-blue'
  | 'light-green'

interface ColorScheme {
  /** 用於聊天氣泡底色（接近 tldraw note 色但稍亮） */
  bubbleBg: string
  /** 用於 dot / 邊框 / 圖示 */
  accent: string
  /** 文字色（在 bubbleBg 上要可讀） */
  text: string
}

const FALLBACK: ColorScheme = {
  bubbleBg: 'rgb(234 227 217 / 0.6)',
  accent: 'rgb(138 133 128)',
  text: 'rgb(26 26 26)',
}

const SCHEMES: Record<StickyColorToken, ColorScheme> = {
  yellow:        { bubbleBg: '#FAE9B0', accent: '#9A6A1A', text: '#3F2E0E' },
  orange:        { bubbleBg: '#F8D5B0', accent: '#9A5A1A', text: '#3F1F0A' },
  green:         { bubbleBg: '#D8E8AA', accent: '#5A7A20', text: '#1F3010' },
  blue:          { bubbleBg: '#C8DDE0', accent: '#3A6878', text: '#142433' },
  violet:        { bubbleBg: '#F5D0E4', accent: '#904870', text: '#3F1028' },
  red:           { bubbleBg: '#F6E5DC', accent: '#7A5040', text: '#3A2010' },
  'light-blue':  { bubbleBg: '#D7E8F2', accent: '#5A8AA5', text: '#1B2F3E' },
  'light-green': { bubbleBg: '#DCEACB', accent: '#7A9D5C', text: '#243515' },
}

export function getColorScheme(
  token: string | null | undefined,
): ColorScheme {
  if (!token) return FALLBACK
  return SCHEMES[token as StickyColorToken] ?? FALLBACK
}
