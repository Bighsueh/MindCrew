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
// 文案改為白話：避免 Discover/Develop/HMW/POV/brainstorm 等專業詞，
// 改用「了解使用者 / 想各種解法」這類白話。
export function getCoachIntro(stage: DTStage | undefined): string {
  switch (stage) {
    case 'discover':
      return '嗨我是你的設計思考小幫手。現在是 Discover（了解使用者）——你想先聊聊要訪談誰、還是怎麼開口問問題？'
    case 'define':
      return '進入 Define（找出問題）了。我們要把訪談聽到的東西整理出幾個關鍵痛點。你想先聊聊怎麼挑重點，還是怎麼寫成好回答的問句？'
    case 'develop':
      return '現在是 Develop（想各種解法）。這一階段點子多比點子好重要，怎麼都丟到白板上都行。你想先聊聊發想規則，還是怎麼讓自己更發散？'
    case 'deliver':
      return '到了 Deliver（做出來測一下）。我們要把想法做成最簡單可以給人試用的版本。你想先想想做什麼形式、還是要找誰來試？'
    default:
      return '嗨我是你的設計思考小幫手。今天有什麼我能幫你想清楚的？'
  }
}
