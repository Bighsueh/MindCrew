// 新 6 桶 micro-phase（Phase 42 C1，spec 22 v2.0 §2.3a）對應的「從這裡開始」hint
// （0.0 暖場由 stage 層 hint 承載，不在本表）。
// 每個 micro 都有 Aria 第一人稱示範 + 4 張師徒制卡片；
// 透過 resolveStageHint(stage, microPhase) 由 stageStartHints.ts 統一取用。
// 文案契約：大白話、無英文縮寫（不講 POV/HMW/Persona）、無投票/線下訪談語
// （全程在系統內用討論＋便條進行，assumption-based）。

import {
  Sparkles,
  Layers,
  Lightbulb,
  Brain,
  Target,
  Users,
  ScrollText,
  Quote,
  Shuffle,
  Ruler,
  ClipboardCheck,
  Compass,
} from 'lucide-react'
import type { MicroPhaseId } from '../../types/models'
import type { StageStartHint } from './stageStartHints'

export const MICRO_PHASE_HINTS: Partial<Record<MicroPhaseId, StageStartHint>> = {
  // ───────────────────── Discover ─────────────────────
  '1.1': {
    stage: 'discover',
    narrative: {
      ariaSays:
        '聊經驗、列對象：先讓每個人講講「自己對這個主題的真實經驗」，再列出「這件事會影響到誰」——把相似的歸成幾群、排好先挖誰後挖誰。',
      example: '我自己用過共享單車，最煩的是「掃了 3 台都騎不動」——那次我沒抱怨給誰聽。',
      delayJudgment: '聊經驗時不要互相評論、也先別討論怎麼解決；列對象時先寫自己想到的，別抄牆上已有的。',
    },
    actions: [
      {
        id: 'ai_warmup',
        title: '請 AI 帶一題聊經驗的問題',
        body: '讓引導者丟一題聊經驗的問題',
        icon: Sparkles,
        recommended: true,
        role: 'modeling',
        scaffold: '像這樣問：「你在這個主題上，有過什麼經驗？」',
        articulation: '先不評論、不談解法，每個人講個一兩分鐘。',
        pitfall: '別馬上跳到「所以我們應該做…」——現在還太早談解決方法。',
      },
      {
        id: 'paste_experience',
        title: '寫下自己的經驗',
        body: '把心裡的經驗講出來',
        icon: ScrollText,
        role: 'scaffolding',
        scaffold: '講「我在什麼情況下做了什麼，當時什麼感覺」；有共鳴的順手貼一兩張',
        articulation: '這是你「親身經歷」的，還是「聽別人說」的？',
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

  '1.2': {
    stage: 'discover',
    narrative: {
      ariaSays:
        '發想痛點與情境：照排好的順序，從最重要的那群開始，想像他們在什麼情況下會卡住、麻煩、受不了；在聊天聊出具體的情境，站得住了再貼成便條、掛在那一群底下。',
      example: '騎機車買晚餐的上班族——結帳那一刻才想起袋子放在家裡，店員已經開始裝塑膠袋了。',
      delayJudgment: '描述「他在哪裡卡住」就好，先不要想「要幫他做什麼」——講到功能就先停一下。',
    },
    actions: [
      {
        id: 'ai_pain_prompt',
        title: '請 AI 帶痛點發想',
        body: '從最重要的那群開始想',
        icon: Sparkles,
        recommended: true,
        role: 'modeling',
        scaffold: '想三件事：他是誰、在什麼情況、卡在哪',
        articulation: '這個情境夠具體嗎？講得出當下的畫面嗎？',
        pitfall: '太空泛的痛點（「很麻煩」「不方便」）幫不上忙——把場景講出來。',
      },
      {
        id: 'chat_then_post',
        title: '聊定才貼',
        body: '聊出站得住的情境再上牆',
        icon: ScrollText,
        role: 'scaffolding',
        scaffold: '在聊天室聊出一個具體情境，大家覺得站得住了，再貼成便條、掛在那一群底下',
        articulation: '這條是大家聊出來的，還是你一個人想的？',
        pitfall: '不用每句話都貼——便條是沉澱後的情境，不是逐字對白。',
      },
      {
        id: 'cover_priority_groups',
        title: '重要的群先顧到',
        body: '排「高」的每群至少想一兩條',
        icon: Users,
        role: 'scaffolding',
        scaffold: '照排好的順序輪流想，排「高」的群先湊到一兩條',
        articulation: '哪一群到現在還一條都沒有？',
        pitfall: '別全擠在同一群——重要的群空著，等下挑問題會沒料。',
      },
      {
        id: 'honest_guess',
        title: '老實說是推想',
        body: '推想沒關係，誠實就好',
        icon: Quote,
        role: 'coaching',
        scaffold: '這些是依經驗和常識的合理推想——講的時候帶一點「我猜」「我想像中他會…」',
        articulation: '這條是親身經驗，還是推想？',
        pitfall: '推想沒關係，但別講得像親眼看過——之後可以找真實的使用者確認。',
      },
    ],
  },

  // ───────────────────── Define ─────────────────────
  '2.1': {
    stage: 'define',
    narrative: {
      ariaSays:
        '痛點歸類：剛剛的痛點是按「人」掛的，現在改按「在講同一件事」來放——不同人但卡在同一件事的，拖到一起，幫每群取個主題名稱。',
      example: '「結帳才想到沒帶」跟「出門前就忘了」——一個發生在店裡、一個在家門口，但都在講「想起來的時機太晚」。',
      delayJudgment: '這關以搬動為主，先別急著貼新便條——整理現成的痛點就好。',
    },
    actions: [
      {
        id: 'drag_and_say',
        title: '拖一張、說一句',
        body: '搬便條時講出你的理由',
        icon: Shuffle,
        recommended: true,
        role: 'scaffolding',
        scaffold: '挑一張痛點拖到你覺得同一掛的旁邊，然後在聊天室說一句為什麼',
        articulation: '這幾張共通的，是同一件事嗎？',
        pitfall: '只拖不說大家會跟不上——「拖」和「說」兩件都做。',
      },
      {
        id: 'name_theme',
        title: '幫每群取主題名稱',
        body: '一句大家看得懂的短語',
        icon: Layers,
        role: 'scaffolding',
        scaffold: '幫歸好的一群痛點取個名字，像「出門前就忘了帶」',
        articulation: '這群在講同一件什麼事？一句話說得出來嗎？',
        pitfall: '別貼個大標籤把差異蓋掉——說不出共通點就先別硬湊。',
      },
      {
        id: 'cross_person',
        title: '跨「人」找同一件事',
        body: '不同人也可能卡在同一處',
        icon: Users,
        role: 'modeling',
        scaffold: '不同利害關係人、但卡在同一件事的痛點，可以放成一群',
        articulation: '這個主題，影響到的是哪幾種人？',
        pitfall: '別硬把不相干的湊一群——主題是浮現出來的，不是擠出來的。',
      },
      {
        id: 'leftover_ok',
        title: '歸不進去的先放著',
        body: '孤張不用硬塞',
        icon: Compass,
        role: 'coaching',
        scaffold: '暫時歸不進去的，放在「還沒歸類的痛點」旁邊就好',
        articulation: '它是真的獨立，還是只是還沒想到歸哪？',
        pitfall: '別為了牆面乾淨硬塞——孤張也可能是一個新主題的種子。',
      },
    ],
  },

  '2.2': {
    stage: 'define',
    narrative: {
      ariaSays:
        '問題定義與深掘：把痛點寫成一句完整的話——「某使用者 需要 某需求，因為 某洞察」；寫完對每句多問幾次為什麼，再看看市面上已經有什麼。',
      example:
        '常騎機車買晚餐的上班族 需要 出門時不用特別想也能帶到袋子的方法，因為 他們不是不想帶，是想到的時候人已經在店裡了。',
      delayJudgment: '一講到「做一個／應該要／設計」這類字眼就先停一下——那是答案，不是問題。',
    },
    actions: [
      {
        id: 'write_problem_statement',
        title: '寫一句問題定義',
        body: '把痛點變成完整的一句話',
        icon: Target,
        recommended: true,
        role: 'modeling',
        scaffold: '句型：「某使用者 需要 某需求，因為 某洞察」；各寫各的、不互抄',
        articulation: '為什麼這個需求，對「這一位」使用者來說是真的？',
        pitfall: '「因為」後面要講出你的發現，不能只是把需求換句話再說一次；是猜的就老實講是猜的。',
      },
      {
        id: 'cite_pain_points',
        title: '點選參考的痛點',
        body: '讓大家知道這句的根據',
        icon: Quote,
        role: 'scaffolding',
        scaffold: '寫之前，點選你參考的那幾張痛點便條（至少兩張），或在聊天講清楚是看了哪幾張寫的',
        articulation: '這句話是從哪幾張痛點來的？',
        pitfall: '沒有根據的問題定義只是想像——回頭把痛點補起來。',
      },
      {
        id: 'socratic_why',
        title: '一直追問為什麼',
        body: '往下挖出根源',
        icon: Brain,
        role: 'scaffolding',
        scaffold: '對每句問題定義，多問幾次「為什麼會這樣」',
        articulation: '問到第 3 次時，答案還停在表面嗎？',
        pitfall: '別問一次就停——表面看到的，通常不是真正的問題。',
      },
      {
        id: 'check_existing',
        title: '盤點現有解法',
        body: '市面上已經有什麼？',
        icon: Compass,
        role: 'coaching',
        scaffold: '把現況分成：已經解決好了／解決一半／還沒人解決',
        articulation: '我們的問題，打的是哪一塊還沒被解決的缺口？',
        pitfall: '引述既有做法可以講，自己冒新方案先忍住——還沒到想解法的時候。',
      },
    ],
  },

  '2.3': {
    stage: 'define',
    narrative: {
      ariaSays:
        '訂準則、收斂與設計題目：先講好用什麼尺來挑（準則），對著準則討論、把最值得做的一到三句搬進選定區，最後改寫成「我們可以怎麼…？」的設計題目。',
      example: '準則：影響範圍｜衡量方式：這個問題每天有多少人遇到。',
      delayJudgment: '挑問題靠討論和準則、不靠直覺表決；談出共識才搬，最後由你拍板。',
    },
    actions: [
      {
        id: 'define_criteria',
        title: '先訂準則',
        body: '先說清楚「用什麼尺來量」',
        icon: Ruler,
        recommended: true,
        role: 'scaffolding',
        scaffold: '格式：「準則：名稱｜衡量方式：怎麼量」；先湊出兩三條',
        articulation: '如果只能留一句問題定義，你最在乎它什麼？',
        pitfall: '別挑完才補準則——順序反過來，等於只是替直覺找理由。',
      },
      {
        id: 'move_to_selection',
        title: '搬進選定區＋寫理由',
        body: '談定一句就搬下去',
        icon: Shuffle,
        role: 'scaffolding',
        scaffold: '談出共識的那句搬進下面的選定區，旁邊配一張「為什麼選它」的便條（寫清楚符合哪條準則）',
        articulation: '這句符合哪一條準則？',
        pitfall: '留太多會想不完——收斂到一到三句；理由要指得出準則。',
      },
      {
        id: 'rewrite_design_question',
        title: '改寫成「我們可以怎麼…？」',
        body: '把問題變成好回答的問句',
        icon: Lightbulb,
        role: 'modeling',
        scaffold: '一句問題定義配一張設計題目：「我們可以怎麼，幫〔某群人〕達到〔某個狀態〕？」',
        articulation: '你的問句裡，是不是又偷偷塞了答案？',
        pitfall: '「做一個 App」不是問題、是答案——把句子拉回「使用者需要什麼」。',
      },
      {
        id: 'final_confirm',
        title: '最後由你確認',
        body: '看過設計題目再點頭',
        icon: ClipboardCheck,
        role: 'coaching',
        scaffold: '看一下這句設計題目，可以的話回「可以」，想改哪個詞直接說',
        articulation: '對著這句題目，你想得出至少三個方向嗎？',
        pitfall: '別不好意思改——這句題目是接下來想點子的起點。',
      },
    ],
  },

}
