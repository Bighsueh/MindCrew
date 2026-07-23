// 新手導引 Modal 文案常數
// 集中於此便於日後 i18n / OpenCC 抽換
//
// 文案契約（Phase 42 D3 / WP10）：大白話、無英文縮寫（不講 POV/HMW/Persona/
// Discover/Define）、無投票、無線下訪談語——全程在系統內用「討論＋便條」進行，
// 痛點與需求是依團隊經驗和常識的合理推想（assumption-based）。口徑對齊
// microPhaseInfo.ts / microPhaseHints.ts。

import type { DTStage } from '../../types/models'

export const ONBOARDING_LEAD_IN = '接下來幾分鐘，我們會帶你看懂這裡發生什麼事。'

export const DT_DEFINITION =
  '設計思考（Design Thinking）是一種以使用者為中心的方法：先「找對問題」、再想答案。我們沒有現場訪談，靠團隊的真實經驗與合理推想出發。本工作坊聚焦第一鑽石——把問題找對、講清楚。'

export const DOUBLE_DIAMOND_NARRATIVE = [
  '活動會先用一段「暖場」破冰熱身，再正式走進「第一鑽石」。',
  '第一鑽石的精神是「先打開、再收攏」，目標是「找對問題」——問對問題比急著想答案更重要。',
  '前半「發現」：盡量打開、先不做決定，從自己的經驗出發，想像會被影響的人在哪裡卡住。',
  '後半「定義」：慢慢收攏，把痛點收成一句清楚的設計題目；靠討論和準則收斂，全程不投票。',
  '最後產出一到三句「我們可以怎麼…？」的設計題目，當作下一步發想的起點。',
]

export interface PhaseDescription {
  id: 'p0' | 'warmup' | 'p1' | 'p2'
  label: string
  shape: '前置' | '暖身' | '發散' | '收斂'
  body: string
}

export const PHASE_DESCRIPTIONS: PhaseDescription[] = [
  {
    id: 'p0',
    label: '開始之前 · 前置',
    shape: '前置',
    body: '確定主題、由 AI 組長帶隊，為第一鑽石做準備。',
  },
  {
    id: 'warmup',
    label: '暖場 · 破冰熱身',
    shape: '暖身',
    body: '正式進主題前先暖身——組長會宣布一個團隊目標（大家一起衝量、湊滿一定數量的「另類用途」），自己也會先示範貼一張便條。越多越意想不到越好，沒有標準答案、亂猜也行，重點是把腦袋打開、跟隊友熟一下。',
  },
  {
    id: 'p1',
    label: '發現 · 同理',
    shape: '發散',
    body: '先聊聊自己對這主題的真實經驗，再列出「這件事會影響到誰」、歸成幾群、排好先後；接著想像每群人在什麼情況下會卡住。沒有現場訪談，這些是依經驗和常識的合理推想。',
  },
  {
    id: 'p2',
    label: '定義 · 聚焦',
    shape: '收斂',
    body: '把痛點按「同一件事」重新歸群，寫成「某使用者 需要 某需求，因為 某洞察」，再對著講好的準則討論、把最值得做的搬進選定區，最後改寫成「我們可以怎麼…？」的設計題目（全程不投票）。',
  },
]

export const COLLAB_NOTE =
  '全程由 AI 組長帶節奏：要進到下一步時，由組長當場宣布推進，不是系統偷偷自動切。各關都有時間上限，時間到組長會誠實收尾、帶大家往下走。'

export const DUAL_TOOL_NOTE =
  '你有兩個基本工具：① 在白板上「貼便條」記下沉澱後的想法、② 在聊天室「發言」一起討論。建議先貼一張便條，再到聊天室說說你的想法。'

export const TASK_BANNER_NOTE =
  '聊天室上方會釘一塊「你的任務」提示，告訴你現在這一步該做什麼（洗版也不會消失）；需要你點頭時，直接按「可以／我想改」就行。'

export const STAGE_NEXT_HINT: Record<DTStage, string> = {
  warmup:
    '先別急著進主題——跟著組長玩一場暖身衝量小遊戲（一起想「這東西還能拿來幹嘛」），把腦袋打開、和隊友熟悉一下，再正式開始。',
  discover:
    '請從「聊經驗、列對象」開始：先聊聊自己真實遇過的經驗，再把「會被影響的人」一個一個貼成便條（便條只寫名字，為什麼相關用聊天說）。',
  define:
    '請把痛點寫成一句「某使用者 需要 某需求，因為 某洞察」，再對著準則討論、收成「我們可以怎麼…？」的設計題目。',
  completed: '第一鑽石完成。可以回顧這幾句設計題目，看看下一步可以延伸到哪裡。',
}

export const STAGE_HEADING_LABEL: Record<DTStage, string> = {
  warmup: '暖場',
  discover: '發現',
  define: '定義',
  completed: '已完成',
}
