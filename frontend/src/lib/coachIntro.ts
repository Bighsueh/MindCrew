import type { DTStage } from '../types/models'

/**
 * 取得 DT 教練的 UX intro 提示文字（依當前 stage 微調）。
 *
 * 重要：此文字**僅用於前端 UI 呈現**——
 * - 不寫入 chatStore
 * - 不寫入 DB
 * - 不送 WS
 *
 * 當 personal channel 為空時，ChatPanel 以此文字渲染一條 empty-state 訊息；
 * 使用者一旦真的送出第一句，該文字立即消失（被真實 messages 列表取代）。
 *
 * 決議來源：specs/13-personal-chat.md §10 OQ1。
 */
export function getCoachIntro(stage: DTStage | undefined): string {
  switch (stage) {
    case 'discover':
      return '嗨我是 DT 教練。Discover 階段重點是同理使用者——你目前在思考要訪談誰、還是怎麼設計訪談？'
    case 'define':
      return 'Define 階段了！我們要從訪談洞察萃取出明確的問題。你想先聊聊聚焦痛點、還是 POV 句型？'
    case 'develop':
      return 'Develop 階段歡迎你！這裡盡情發想各種解法。要先做 brainstorm 規則、還是怎麼讓點子更發散？'
    case 'deliver':
      return 'Deliver 階段。要把想法做成原型給人測試。你想先決定原型形式、還是測試對象？'
    default:
      return '嗨我是 DT 教練。今天有什麼我能幫你想清楚的？'
  }
}
