import type { ReactNode } from 'react'

// D2/WP9 #12（spec 05 §10.2 / 06 §3.1 v4.25）：聊天訊息強調格式。
// 支援的 markdown 子集：**粗體**、__底線__。
// - emphasize=true（**僅 supervisor**）：渲染為 <strong>／<u>。
// - emphasize=false（crew／人類）：去除標記、純文字顯示（spec：即使帶標記也一律去格式，
//   維持組長引導者的視覺權威與一致性）。
//
// 以 React 元素組裝（非 dangerouslySetInnerHTML）→ 文字一律由 React 轉義，XSS 安全。
// 標記內不允許巢狀同類標記或換行（保守、避免貪婪誤吃整段）。
const EMPHASIS_TOKEN = /(\*\*[^*\n]+?\*\*|__[^_\n]+?__)/g

export function renderEmphasis(content: string, emphasize: boolean): ReactNode {
  // 無標記快路徑（絕大多數訊息）。
  if (!content || (!content.includes('**') && !content.includes('__'))) {
    return content
  }

  // split（單一捕獲組）：真正被 regex 命中的 token 落在奇數 index、未命中片段（literal）
  // 落在偶數 index。只把奇數 index 當強調 token——它已由 regex 保證單行、無同類巢狀，
  // 不必再做較鬆的 startsWith/endsWith 形狀檢查（避免「整段以 ** 開頭結尾但中間跨行、
  // regex 沒命中而 split 回整串」被誤判成一個 token 而把整段標起來）。
  const parts = content.split(EMPHASIS_TOKEN)
  return parts.map((part, i) => {
    if (i % 2 === 0) return part // literal 段，原樣輸出（React 轉義）
    const inner = part.slice(2, -2)
    if (part.startsWith('**')) return emphasize ? <strong key={i}>{inner}</strong> : inner
    return emphasize ? <u key={i}>{inner}</u> : inner // 必為 __…__
  })
}
