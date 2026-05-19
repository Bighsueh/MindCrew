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
  yellow:        { bubbleBg: '#FBEFC8', accent: '#C58B1A', text: '#3F2E0E' },
  orange:        { bubbleBg: '#FBDCC0', accent: '#C76A1A', text: '#3F2110' },
  green:         { bubbleBg: '#D6E5BD', accent: '#6B8B3A', text: '#27310E' },
  blue:          { bubbleBg: '#C6DCEC', accent: '#3F6E96', text: '#142433' },
  violet:        { bubbleBg: '#D9CFE5', accent: '#7A5BAA', text: '#2A1F40' },
  red:           { bubbleBg: '#F2C9C5', accent: '#B14238', text: '#3F1612' },
  'light-blue':  { bubbleBg: '#D7E8F2', accent: '#5A8AA5', text: '#1B2F3E' },
  'light-green': { bubbleBg: '#DCEACB', accent: '#7A9D5C', text: '#243515' },
}

export function getColorScheme(
  token: string | null | undefined,
): ColorScheme {
  if (!token) return FALLBACK
  return SCHEMES[token as StickyColorToken] ?? FALLBACK
}
