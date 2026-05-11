// Motion design tokens — keep in sync with src/index.css custom properties.
//
// 使用情境（中文）：
//   1. 在 JS/TS 計算需要時間值（setTimeout、Framer Motion 等）；
//   2. 統一動畫時長／緩動，避免散落 magic number；
//   3. 由 useReducedMotion() 決定是否回退。

export const duration = {
  instant: 100,
  fast: 150,
  base: 200,
  normal: 250,
  panel: 300,
  slow: 400,
  ambientShort: 1500,
  ambient: 2000,
  ambientLong: 3000,
} as const

export const easing = {
  standard: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
  enter: 'cubic-bezier(0, 0, 0.2, 1)',
  exit: 'cubic-bezier(0.4, 0, 1, 1)',
  smooth: 'cubic-bezier(0.4, 0, 0.2, 1)',
  out: 'cubic-bezier(0.16, 1, 0.3, 1)',
} as const

export const stagger = {
  step: 50,
  fast: 30,
  slow: 80,
} as const

/** Stagger child 的 inline style helper，給 CSS variable 用。 */
export function staggerStyle(index: number, step: number = stagger.step): React.CSSProperties {
  return { ['--stagger-index' as string]: index, ['--stagger-step' as string]: `${step}ms` }
}
