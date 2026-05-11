import { useEffect, useState } from 'react'
import {
  Sparkles,
  ClipboardPaste,
  LayoutTemplate,
  Copy,
  Layers,
  Lightbulb,
  Map,
  User,
  Pencil,
  Brain,
  Vote,
  Frame,
  TestTube,
  ListChecks,
  Video,
  type LucideIcon,
} from 'lucide-react'
import { staggerStyle, stagger, duration } from '../../lib/motion'
import { useReducedMotion } from '../../hooks/useReducedMotion'

// 起手式階段識別字串（與 DTStage 對齊；不可任意擴充）
export type StartActionStage = 'discover' | 'define' | 'develop' | 'deliver'

// 單張動作卡片資料
export interface StartAction {
  id: string
  title: string
  body: string
  icon: LucideIcon
  recommended?: boolean
}

// 各 DT 階段對應的「起手式」候選動作（每階段 4 張，其中 1 張 recommended）
export const STAGE_ACTIONS: Record<StartActionStage, StartAction[]> = {
  discover: [
    { id: 'ai_start', title: '請 AI 起頭', body: '讓 Aria 草擬訪談大綱', icon: Sparkles, recommended: true },
    { id: 'paste_transcript', title: '貼上訪談逐字稿', body: '從文字檔產生洞察便利貼', icon: ClipboardPaste },
    { id: 'use_template', title: '從訪談模板開始', body: '5W1H 訪談結構', icon: LayoutTemplate },
    { id: 'copy_from_previous', title: '從先前專案複製', body: '重用過去的訪談洞察', icon: Copy },
  ],
  define: [
    { id: 'cluster_insights', title: '歸納訪談洞察', body: '把便利貼分群找模式', icon: Layers, recommended: true },
    { id: 'write_hmw', title: '撰寫 HMW 問題', body: 'How Might We 句型', icon: Lightbulb },
    { id: 'user_journey', title: '畫使用者旅程', body: 'user journey map 模板', icon: Map },
    { id: 'create_persona', title: '建立 persona', body: '代表性使用者卡', icon: User },
  ],
  develop: [
    { id: 'crazy_eights', title: 'Crazy 8s', body: '8 分鐘畫 8 個構想', icon: Pencil, recommended: true },
    { id: 'brainstorm', title: '腦力激盪', body: '自由發散構想', icon: Brain },
    { id: 'ai_propose', title: '請 AI 提案', body: '讓 Aria 提供候選解法', icon: Sparkles },
    { id: 'dot_vote', title: '點點投票', body: '標記最有潛力的方向', icon: Vote },
  ],
  deliver: [
    { id: 'lowfi_prototype', title: '製作低保真原型', body: '畫 wireframe 或畫面草圖', icon: Frame, recommended: true },
    { id: 'plan_testing', title: '規劃使用者測試', body: '決定要驗證的假設', icon: TestTube },
    { id: 'write_tasks', title: '寫測試任務', body: '受測者要完成的步驟', icon: ListChecks },
    { id: 'record_pitch', title: '拍攝展示影片', body: '1 分鐘原型展示腳本', icon: Video },
  ],
}

// 階段中文名稱
export const STAGE_LABEL: Record<StartActionStage, string> = {
  discover: '發掘',
  define: '定義',
  develop: '發想',
  deliver: '交付',
}

// 階段副標：解釋該階段該做什麼
const STAGE_SUBTITLE: Record<StartActionStage, string> = {
  discover: '從訪談與觀察中蒐集第一手洞察',
  define: '把雜訊收斂成清楚的問題陳述',
  develop: '展開可能性，產出多元的解法',
  deliver: '把概念變成可被驗證的原型',
}

// 離場淡出時間（與 transition-opacity 對齊）
const EXIT_DURATION = duration.normal

export interface StartActionGridProps {
  actions: StartAction[]
  onActionClick?: (actionId: string) => void
  /** dense=true: 小卡（popover 場景）；dense=false: 大卡（banner 場景） */
  dense?: boolean
  /** 控制 stagger 是否啟用（reduced-motion 時關閉） */
  animate?: boolean
  /** 反向 stagger（離場時用） */
  reverseStagger?: boolean
}

/** 共用卡片網格 — banner 與 popover 都用它。 */
export function StartActionGrid({
  actions,
  onActionClick,
  dense = false,
  animate = true,
  reverseStagger = false,
}: StartActionGridProps) {
  return (
    <div
      className={
        animate
          ? `grid w-full grid-cols-1 gap-${dense ? '2' : '3'} sm:grid-cols-2 stagger-children`
          : `grid w-full grid-cols-1 gap-${dense ? '2' : '3'} sm:grid-cols-2`
      }
    >
      {actions.map((action, i) => {
        const Icon = action.icon
        const staggerIndex = reverseStagger ? actions.length - 1 - i : i
        const card = (
          <button
            type="button"
            onClick={() => onActionClick?.(action.id)}
            className={
              dense
                ? 'card-hover-warm pointer-events-auto flex w-full flex-col gap-1 rounded-lg border border-border bg-surface p-2.5 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-accent'
                : 'card-hover-warm pointer-events-auto flex min-h-[100px] min-w-[140px] w-full flex-col gap-1.5 rounded-xl border border-border bg-surface p-3 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-accent'
            }
            style={animate ? staggerStyle(staggerIndex, stagger.fast) : undefined}
          >
            <Icon size={dense ? 16 : 20} className="text-accent" aria-hidden="true" />
            <span className={dense ? 'text-xs font-medium text-text' : 'text-sm font-medium text-text'}>
              {action.title}
            </span>
            <span className={dense ? 'text-[10px] text-text-muted line-clamp-1' : 'text-xs text-text-muted line-clamp-1'}>
              {action.body}
            </span>
          </button>
        )
        if (action.recommended) {
          return (
            <div
              key={action.id}
              className={`pointer-events-none rounded-xl ${animate ? 'animate-pulse-outline' : ''}`}
            >
              {card}
            </div>
          )
        }
        return <div key={action.id} className="pointer-events-none">{card}</div>
      })}
    </div>
  )
}

export interface CanvasEmptyStateProps {
  stage: StartActionStage
  visible: boolean
  onActionClick?: (actionId: string) => void
  /** 當 banner 從可見變為不可見時觸發（用於父層在白板出現第一張便利貼後，
   *  在 StageHintBar 的 [起頭] chip 上播一次 flash，教學「起手式搬到這裡」）。 */
  onHide?: () => void
}

export function CanvasEmptyState({ stage, visible, onActionClick, onHide }: CanvasEmptyStateProps) {
  const reducedMotion = useReducedMotion()
  const [mounted, setMounted] = useState<boolean>(visible)
  const [exiting, setExiting] = useState<boolean>(false)

  useEffect(() => {
    if (visible) {
      setMounted(true)
      setExiting(false)
      return
    }
    if (!mounted) return
    if (reducedMotion) {
      setMounted(false)
      onHide?.()
      return
    }
    setExiting(true)
    const t = setTimeout(() => {
      setMounted(false)
      setExiting(false)
      onHide?.()
    }, EXIT_DURATION)
    return () => clearTimeout(t)
  }, [visible, mounted, reducedMotion, onHide])

  if (!mounted) return null

  const actions = STAGE_ACTIONS[stage]
  const stageLabel = STAGE_LABEL[stage]
  const subtitle = STAGE_SUBTITLE[stage]

  const useStagger = !reducedMotion && !exiting

  return (
    <div
      className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center px-6"
      aria-hidden={!visible}
    >
      <div
        className="flex max-w-md flex-col items-center gap-4 transition-opacity"
        style={{
          opacity: exiting ? 0 : 1,
          transitionDuration: `${EXIT_DURATION}ms`,
        }}
      >
        <div className="flex flex-col items-center gap-1 text-center">
          <span className="text-xs uppercase tracking-wide text-text-muted">
            起手式 · {stageLabel} 階段
          </span>
          <h2 className="text-lg font-semibold text-text">從這裡開始</h2>
          <p className="text-sm text-text-muted">{subtitle}</p>
        </div>

        <StartActionGrid
          actions={actions}
          onActionClick={onActionClick}
          animate={useStagger}
          reverseStagger={exiting}
        />
      </div>
    </div>
  )
}

export default CanvasEmptyState
