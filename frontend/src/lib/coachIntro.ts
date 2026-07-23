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
 * 決議來源： OQ1。
 */
// 文案改為白話：避免 Discover/Define/HMW/POV/訪談/brainstorm 等專業詞與線下調查語，
// 改用「了解使用者 / 找出問題」這類白話（assumption-based，無現場訪談）。
export function getCoachIntro(stage: DTStage | undefined): string {
  switch (stage) {
    case 'discover':
      return '嗨我是你的設計思考小幫手。現在是「了解使用者」的階段——我們沒有現場訪談，靠大家的經驗和想像。你想先聊聊自己遇過的經驗，還是先想想這件事會影響到誰？'
    case 'define':
      return '進入「找出問題」的階段了。我們把剛剛想到的痛點整理成幾個關鍵重點，再收成一句清楚的問題。你想先聊聊怎麼分群，還是怎麼把問題講清楚？'
    case 'completed':
      return '第一鑽石的旅程完成了——你們已經把問題聚焦得很清楚了。要不要回顧一下這幾句設計題目，看看下一步可以延伸到哪裡？'
    default:
      return '嗨我是你的設計思考小幫手。今天有什麼我能幫你想清楚的？'
  }
}
