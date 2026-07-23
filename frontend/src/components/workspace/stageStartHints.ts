// 「從這裡開始」共用設定 — 認知師徒制 × Double Diamond
// 依據 /Users/hsueh/Code/research/MeetingRecord/dt-flow-spec/dt-flow-spec-v4.md
//
// 設計原則：
// - Modeling：Aria 以第一人稱示範「我會這樣開始」
// - Scaffolding：每張卡片標出該用的結構模板
// - Articulation：強制使用者說清楚此刻該說的事
// - Coaching：pitfall 提醒常見陷阱
// - Reflection / Exploration：延後判斷型引導

import {
  Sparkles,
  ScrollText,
  Users,
  Layers,
  Lightbulb,
  Ruler,
  Target,
  type LucideIcon,
} from 'lucide-react'

// Phase 29 (spec/04-06 §4.10): develop / deliver removed alongside the second diamond.
export type StartActionStage = 'discover' | 'define'

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
  discover: '發現',
  define: '定義',
}

export const STAGE_SUBTITLE: Record<StartActionStage, string> = {
  discover: '從大家的經驗出發，找出會被影響的人、想像他們卡在哪',
  define: '從一堆痛點裡，挑出幾個最關鍵、講得清楚的問題',
}

export const ROLE_LABEL: Record<ApprenticeshipRole, string> = {
  modeling: '示範',
  scaffolding: '範本',
  coaching: '指導',
  articulation: '說清楚',
  reflection: '反思',
}

export const STAGE_START_HINTS: Record<StartActionStage, StageStartHint> = {
  discover: {
    stage: 'discover',
    narrative: {
      ariaSays:
        '這個階段先別急著解釋、也別急著想解法。先聊聊自己對這主題的真實經驗，再列出「這件事會影響到誰」——把相似的歸成幾群、排好先挖誰後挖誰。',
      example: '我自己用過共享單車，最煩的是「掃了 3 台都騎不動」——那次我沒抱怨給誰聽。',
      delayJudgment: '聊經驗時先別互相評論、也先別討論怎麼解決——現在還太早談解法。',
    },
    actions: [
      {
        id: 'ai_start',
        title: '請 AI 起頭',
        body: '讓小幫手帶一題聊經驗的問題',
        icon: Sparkles,
        recommended: true,
        role: 'modeling',
        scaffold: '像這樣問：「你在這個主題上，有過什麼經驗？」',
        articulation: '我們想了解誰？想知道什麼？',
        pitfall: '別馬上跳到「所以我們應該做…」——現在還太早談解決方法。',
      },
      {
        id: 'share_experience',
        title: '寫下自己的經驗',
        body: '把心裡的經驗講出來',
        icon: ScrollText,
        role: 'scaffolding',
        scaffold: '講「我在什麼情況下做了什麼，當時什麼感覺」；有共鳴的順手貼一兩張',
        articulation: '這是你親身經歷的，還是聽別人說的？',
        pitfall: '別只講一句結論（像「很難用」）——把當時的情況和心情也講出來。',
      },
      {
        id: 'list_stakeholders',
        title: '列「會被影響的人」',
        body: '想到誰，就把名字貼成一張便條',
        icon: Users,
        role: 'scaffolding',
        scaffold: '一張便條只寫名字；為什麼跟這件事有關，用聊天講',
        articulation: '你列的這些人裡，誰是直接受影響、誰是間接的？',
        pitfall: '先把自己想到的倒出來、別抄牆上已有的——重複了系統會提醒你換一個。',
      },
      {
        id: 'group_and_rank',
        title: '歸類，再排先後',
        body: '相似的歸一群，標出先挖誰',
        icon: Layers,
        role: 'coaching',
        scaffold: '口頭講「這幾張一群」牆面會自動排好；每群旁貼「高」「中」「低」小標籤',
        articulation: '哪一群最值得先挖？為什麼？',
        pitfall: '排序不是刪人——所有群都留著，也先不用寫理由。',
      },
    ],
  },

  define: {
    stage: 'define',
    narrative: {
      ariaSays:
        '這個階段先別急著想「要做一個什麼東西」。我們要的是把問題講清楚——把痛點收成一句話，而不是馬上跳到答案。',
      example:
        '一句話講清楚：常騎機車買晚餐的上班族 需要 出門時不用特別想也能帶到袋子的方法，因為 他們不是不想帶，是想到的時候人已經在店裡了。',
      delayJudgment: '聽到「做一個／應該要／設計」這類字眼就先停一下——那是答案，不是問題。',
    },
    actions: [
      {
        id: 'cluster_insights',
        title: '把痛點分群',
        body: '把講同一件事的痛點放在一起',
        icon: Layers,
        recommended: true,
        role: 'scaffolding',
        scaffold: '把相似的痛點拖在一起、幫每群取個主題名稱',
        articulation: '這一群共通的，是同一件事嗎？',
        pitfall: '別急著貼個大標籤把差異蓋掉——說不出共通點就先別硬湊。',
      },
      {
        id: 'write_problem',
        title: '寫一句問題定義',
        body: '把痛點變成完整的一句話',
        icon: Target,
        role: 'modeling',
        scaffold: '句型：「某使用者 需要 某需求，因為 某洞察」；各寫各的、不互抄',
        articulation: '為什麼這個需求，對「這一位」使用者來說是真的？',
        pitfall: '「因為」後面要講出你的發現，不能只是把需求換句話再說一次；是猜的就老實講是猜的。',
      },
      {
        id: 'rewrite_design_question',
        title: '改寫成「我們可以怎麼…？」',
        body: '把問題變成好回答的問句',
        icon: Lightbulb,
        role: 'scaffolding',
        scaffold: '一句問題定義配一張設計題目：「我們可以怎麼，幫〔某群人〕達到〔某個狀態〕？」',
        articulation: '你的問句裡，是不是又偷偷塞了答案？',
        pitfall: '「做一個 App」不是問題、是答案——把句子拉回「使用者需要什麼」。',
      },
      {
        id: 'define_criteria',
        title: '先訂準則再挑',
        body: '先說清楚「用什麼尺來量」',
        icon: Ruler,
        role: 'coaching',
        scaffold: '先講好準則：影響大不大／能學到多少／做不做得到，再對著準則討論挑重點',
        articulation: '你是用什麼準則在排，而不是憑直覺？',
        pitfall: '別挑完才補準則——順序反過來等於替直覺找理由；這關靠討論和準則收斂、不投票。',
      },
    ],
  },

  // Phase 29 (spec/04-06 §4.10): develop / deliver stage hints removed.
}

// 向後相容：保留 STAGE_ACTIONS 命名，導出每階段的 actions list
export const STAGE_ACTIONS: Record<StartActionStage, StartAction[]> = {
  discover: STAGE_START_HINTS.discover.actions,
  define: STAGE_START_HINTS.define.actions,
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
  const microHint = microPhase ? MICRO_PHASE_HINTS[microPhase] : undefined
  if (microHint) {
    return microHint
  }
  return STAGE_START_HINTS[stage]
}
