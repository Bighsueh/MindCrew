// 「從這裡開始」共用設定 — 認知師徒制 × Double Diamond
// 依據 /Users/hsueh/Code/research/MeetingRecord/dt-flow-spec/dt-flow-spec-v4.md
//
// 設計原則：
// - Modeling：Aria 以第一人稱示範「我會這樣開始」
// - Scaffolding：每張卡片標出該用的結構模板
// - Articulation：強制使用者說清楚此刻該說的事
// - Coaching：pitfall 提醒常見陷阱
// - Reflection / Exploration：Deliver 的 Debrief、Discover/Develop 的延後判斷

import {
  Sparkles,
  ClipboardPaste,
  LayoutTemplate,
  Copy,
  Layers,
  Lightbulb,
  Pencil,
  Brain,
  Vote,
  Frame,
  TestTube,
  ListChecks,
  Repeat,
  Target,
  type LucideIcon,
} from 'lucide-react'

export type StartActionStage = 'discover' | 'define' | 'develop' | 'deliver'

export type ApprenticeshipRole =
  | 'modeling'
  | 'scaffolding'
  | 'coaching'
  | 'articulation'
  | 'reflection'

export interface StartAction {
  id: string
  title: string
  body: string
  icon: LucideIcon
  recommended?: boolean
  role: ApprenticeshipRole
  scaffold: string
  articulation: string
  pitfall?: string
}

export interface StageNarrative {
  ariaSays: string
  example: string
  delayJudgment?: string
}

export interface StageStartHint {
  stage: StartActionStage
  narrative: StageNarrative
  actions: StartAction[]
}

export const STAGE_LABEL: Record<StartActionStage, string> = {
  discover: '發掘',
  define: '定義',
  develop: '發想',
  deliver: '交付',
}

export const STAGE_SUBTITLE: Record<StartActionStage, string> = {
  discover: '從訪談與觀察中蒐集第一手洞察',
  define: '把雜訊收斂成清楚的問題陳述',
  develop: '展開可能性，產出多元的解法',
  deliver: '把概念變成可被驗證的原型',
}

export const ROLE_LABEL: Record<ApprenticeshipRole, string> = {
  modeling: '示範',
  scaffolding: '鷹架',
  coaching: '教練',
  articulation: '說清楚',
  reflection: '反思',
}

export const STAGE_START_HINTS: Record<StartActionStage, StageStartHint> = {
  discover: {
    stage: 'discover',
    narrative: {
      ariaSays:
        '在發掘階段，我們不急著解釋——先把「聽到什麼、看到什麼」原音保留，之後才解讀。',
      example: '〔受訪者・3:42〕「我每天要按 18 次才能扣到款」　情緒：無奈',
      delayJudgment: '先觀察、後歸因；先記原句、後寫解讀。',
    },
    actions: [
      {
        id: 'ai_start',
        title: '請 AI 起頭',
        body: '讓 Aria 草擬訪談大綱',
        icon: Sparkles,
        recommended: true,
        role: 'modeling',
        scaffold: '5W1H 訪談大綱',
        articulation: '我們要研究誰？想知道什麼？',
        pitfall: '別讓 AI 替你決定要問誰——先把研究對象寫清楚再交給它擴寫。',
      },
      {
        id: 'paste_transcript',
        title: '貼上訪談逐字稿',
        body: '從文字檔產生洞察便利貼',
        icon: ClipboardPaste,
        role: 'scaffolding',
        scaffold: '〔人・時間〕「原句」＋情緒',
        articulation: '哪句是事實？哪句是你的解讀？',
        pitfall: '不要把推測寫成引用——原句要打引號，解讀另外註記。',
      },
      {
        id: 'use_template',
        title: '從訪談模板開始',
        body: '5W1H 訪談結構',
        icon: LayoutTemplate,
        role: 'scaffolding',
        scaffold: 'Empathy Map／Persona／Journey',
        articulation: '此模板裡哪一格現在最空？',
        pitfall: '模板是骨架不是答案，先用觀察填空，別用想像補滿。',
      },
      {
        id: 'copy_from_previous',
        title: '從先前專案複製',
        body: '重用過去的訪談洞察',
        icon: Copy,
        role: 'coaching',
        scaffold: '借用 Insight，而非結論',
        articulation: '上次的脈絡跟這次一樣嗎？',
        pitfall: '結論會過期，洞察才可遷移——先檢視「為什麼上次成立」。',
      },
    ],
  },

  define: {
    stage: 'define',
    narrative: {
      ariaSays:
        '定義階段我會先把「解法語言」擋下來。我們要的是 POV 與 HMW，不是「要做一個 App」。',
      example:
        'POV：〔長照志工〕需要〔快速辨識家屬情緒變化的方法〕，因為〔情緒前兆比症狀更早出現〕。',
      delayJudgment: '紅旗詞：做一個／應該要／設計／build／make——出現就先暫停。',
    },
    actions: [
      {
        id: 'cluster_insights',
        title: '群聚便利貼',
        body: '把便利貼分群找模式',
        icon: Layers,
        recommended: true,
        role: 'scaffolding',
        scaffold: 'Affinity Mapping',
        articulation: '這群的共同主題是「需求」還是「現象」？',
        pitfall: '別用「主題標籤」蓋掉個別差異——先讓張力浮出來。',
      },
      {
        id: 'write_pov',
        title: '草擬 POV',
        body: '寫 Point of View 句型',
        icon: Target,
        role: 'modeling',
        scaffold: '〔User〕需要〔Need〕，因為〔Insight〕',
        articulation: '為什麼這個需求對「這位」用戶為真？',
        pitfall: 'INSIGHT 不能只是把 Need 換句話說，要說出背後的洞察。',
      },
      {
        id: 'write_hmw',
        title: '寫 HMW 問題',
        body: 'How Might We 句型',
        icon: Lightbulb,
        role: 'scaffolding',
        scaffold: 'How Might We …？',
        articulation: '你的 HMW 有沒有偷渡解法？',
        pitfall: '「我們如何做一個 App」不是 HMW，是解法——把句子拉回需求層級。',
      },
      {
        id: 'dot_vote_define',
        title: '投票收斂主題',
        body: '挑出最值得攻的問題',
        icon: Vote,
        role: 'coaching',
        scaffold: '收斂判準（影響力／可學到的事／可行性）',
        articulation: '用什麼客觀標準排序，而不是直覺？',
        pitfall: '投票前先講判準——否則只是把直覺加總。',
      },
    ],
  },

  develop: {
    stage: 'develop',
    narrative: {
      ariaSays:
        '發想階段不討論可行性。我會用「換機制」推你跳出第一波思路。',
      example: '第一波都在「加功能」→ 現在請各出 3 個用「刪步驟」達成同一目的的點子。',
      delayJudgment: '先量、後品；先發散、後篩選。',
    },
    actions: [
      {
        id: 'crazy_eights',
        title: 'Crazy 8s 草圖',
        body: '8 分鐘畫 8 個構想',
        icon: Pencil,
        recommended: true,
        role: 'modeling',
        scaffold: '8 格／8 分鐘',
        articulation: '你卡住的是「沒點子」還是「在自我審查」？',
        pitfall: '第 5 格之後才是真發散——別在第 3 格就放棄。',
      },
      {
        id: 'brainstorm',
        title: 'SCAMPER 變形',
        body: '套用 7 種變形手法',
        icon: Brain,
        role: 'scaffolding',
        scaffold: '替代／組合／調整／修改／別用／消除／反轉',
        articulation: '這個點子用了哪一招？',
        pitfall: '點子標不出招式，往往代表只是直覺重組——回頭挑一招套套看。',
      },
      {
        id: 'ai_propose',
        title: '類別轉換提示',
        body: '請 Aria 換機制再發散',
        icon: Repeat,
        role: 'coaching',
        scaffold: '「現在所有點子都用了 X，請改用 Y 再出 3 個」',
        articulation: '目前所有點子的共同機制是什麼？',
        pitfall: 'AI 容易順著你現有的方向擴寫——逼它換一個機制再生成。',
      },
      {
        id: 'expand_from_hmw',
        title: '從 HMW 發散',
        body: '每條 HMW 至少 5 個點子',
        icon: Sparkles,
        role: 'scaffolding',
        scaffold: '每條 HMW × N 構想',
        articulation: '是不是只圍著一條 HMW 在打轉？',
        pitfall: '別讓最熱門的 HMW 吃掉時間——冷門 HMW 才是差異化來源。',
      },
    ],
  },

  deliver: {
    stage: 'deliver',
    narrative: {
      ariaSays:
        '交付前我會逼大家寫「假設卡」。沒寫清楚要測什麼，就不能進原型。',
      example:
        '假設：用戶願意每天花 30 秒記錄情緒。成功＝連續 7 天回填率 ≥ 60%；失敗＝第 3 天起回填率歸零。',
    },
    actions: [
      {
        id: 'write_hypothesis',
        title: '寫假設卡',
        body: '把要驗證的事說清楚',
        icon: Target,
        recommended: true,
        role: 'articulation',
        scaffold: '測試：X／成功＝Y／失敗＝Z／保真度＝…',
        articulation: '你在測「使用者願意」還是「技術做得到」？',
        pitfall: '沒有失敗條件的假設不能驗證——一定要寫出反證會長什麼樣。',
      },
      {
        id: 'write_tasks',
        title: '拆 Task Ticket',
        body: '把假設拆成可執行任務',
        icon: ListChecks,
        role: 'scaffolding',
        scaffold: 'Ticket 模板（Owner／DoD／時限）',
        articulation: '完成定義（DoD）夠不夠客觀？',
        pitfall: '「做完原型」不是 DoD——要寫出「給 5 位使用者各跑一次」這類具體條件。',
      },
      {
        id: 'lowfi_prototype',
        title: '低保真原型',
        body: '挑剛好夠回答假設的保真度',
        icon: Frame,
        role: 'modeling',
        scaffold: '紙原型／Wireframe／Wizard-of-Oz',
        articulation: '為什麼這個保真度就夠回答假設？',
        pitfall: '保真度過高會偷渡解法決策——剛好夠就好。',
      },
      {
        id: 'plan_debrief',
        title: 'Debrief 反思',
        body: '跑完原型用三題收尾',
        icon: TestTube,
        role: 'reflection',
        scaffold: '信念更新？回應了哪條 HMW？下次 Phase 1 怎麼改？',
        articulation: '我們學到什麼能改寫 Phase 1 的事？',
        pitfall: '不要只回顧「結果好不好」——回顧「我們的信念被更新了嗎」。',
      },
    ],
  },
}

// 向後相容：保留 STAGE_ACTIONS 命名，導出每階段的 actions list
export const STAGE_ACTIONS: Record<StartActionStage, StartAction[]> = {
  discover: STAGE_START_HINTS.discover.actions,
  define: STAGE_START_HINTS.define.actions,
  develop: STAGE_START_HINTS.develop.actions,
  deliver: STAGE_START_HINTS.deliver.actions,
}

// ──────────────────────────────────────────────────────────────────────────
// Micro-phase 細粒度 hint resolver
// 有 microPhase 命中 MICRO_PHASE_HINTS 時優先用 micro 版；
// 否則退回 macro stage 的 STAGE_START_HINTS（fallback）。
// ──────────────────────────────────────────────────────────────────────────

import type { MicroPhaseId } from '../../types/models'
import { MICRO_PHASE_HINTS } from './microPhaseHints'

export function resolveStageHint(
  stage: StartActionStage,
  microPhase?: MicroPhaseId | null,
): StageStartHint {
  if (microPhase && MICRO_PHASE_HINTS[microPhase]) {
    return MICRO_PHASE_HINTS[microPhase]
  }
  return STAGE_START_HINTS[stage]
}
