import { useEffect, useRef, useState } from 'react'
import { Info, Sparkles } from 'lucide-react'
import { staggerStyle, stagger, duration } from '../../lib/motion'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import {
  resolveStageHint,
  STAGE_LABEL,
  STAGE_SUBTITLE,
  ROLE_LABEL,
  type StartAction,
  type StartActionStage,
  type StageNarrative,
} from '../workspace/stageStartHints'
import type { MicroPhaseId } from '../../types/models'

// 對外重新導出，避免既有 import 路徑壞掉
export {
  STAGE_ACTIONS,
  STAGE_START_HINTS,
  STAGE_LABEL,
  STAGE_SUBTITLE,
  ROLE_LABEL,
} from '../workspace/stageStartHints'
export type {
  StartAction,
  StartActionStage,
  StageStartHint,
  StageNarrative,
  ApprenticeshipRole,
} from '../workspace/stageStartHints'

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
        const roleLabel = ROLE_LABEL[action.role]

        const card = (
          <button
            type="button"
            onClick={() => onActionClick?.(action.id)}
            className={
              dense
                ? 'card-hover-warm pointer-events-auto group relative flex w-full flex-col gap-1 rounded-lg border border-border bg-surface p-2.5 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-accent'
                : 'card-hover-warm pointer-events-auto group relative flex min-h-[124px] min-w-[160px] w-full flex-col gap-1.5 rounded-xl border border-border bg-surface p-3 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-accent'
            }
            style={animate ? staggerStyle(staggerIndex, stagger.fast) : undefined}
          >
            <div className="flex items-center gap-1.5">
              <Icon size={dense ? 14 : 18} className="text-accent" aria-hidden="true" />
              <span
                className={
                  dense
                    ? 'rounded-sm bg-accent/10 px-1 py-[1px] text-[9px] font-medium uppercase tracking-wide text-accent'
                    : 'rounded-sm bg-accent/10 px-1.5 py-[2px] text-[10px] font-medium uppercase tracking-wide text-accent'
                }
              >
                {roleLabel}
              </span>
            </div>
            <span className={dense ? 'text-xs font-medium text-text' : 'text-sm font-semibold text-text'}>
              {action.title}
            </span>
            <span
              className={
                dense
                  ? 'text-[10px] text-text-muted line-clamp-1'
                  : 'text-xs text-text-muted line-clamp-2'
              }
            >
              {action.scaffold}
            </span>
            {!dense && (
              <span className="mt-auto text-[11px] leading-snug text-text-muted line-clamp-2">
                💬 {action.articulation}
              </span>
            )}
            {action.pitfall && (
              <span
                className={
                  dense
                    ? 'pointer-events-none absolute right-1 top-1 text-text-muted opacity-0 transition-opacity group-hover:opacity-100'
                    : 'pointer-events-none absolute right-1.5 top-1.5 text-text-muted opacity-60 transition-opacity group-hover:opacity-100'
                }
                title={action.pitfall}
                aria-label={`陷阱提醒：${action.pitfall}`}
              >
                <Info size={dense ? 10 : 12} />
              </span>
            )}
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

export interface NarrativeHeaderProps {
  narrative: StageNarrative
  /** dense=true: 折疊成單行（popover 用） */
  dense?: boolean
}

/** Aria 第一人稱示範敘事 — Modeling 區塊 */
export function NarrativeHeader({ narrative, dense = false }: NarrativeHeaderProps) {
  const [expanded, setExpanded] = useState<boolean>(!dense)

  if (dense) {
    return (
      <div className="w-full">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex w-full items-start gap-1.5 rounded-md border border-border bg-bg-warm px-2 py-1.5 text-left text-[11px] leading-snug text-text-muted hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          aria-expanded={expanded}
        >
          <Sparkles size={12} className="mt-[2px] shrink-0 text-accent" aria-hidden="true" />
          <span className="flex-1">
            <span className="font-medium text-text">Aria 示範</span>
            <span className="text-text-muted">　{expanded ? '（收合）' : '（展開）'}</span>
            {!expanded && (
              <span className="block truncate text-text-muted">{narrative.ariaSays}</span>
            )}
          </span>
        </button>
        {expanded && (
          <div className="mt-1.5 rounded-md border border-border bg-bg-warm px-2.5 py-2 text-[11px] leading-relaxed text-text-muted">
            <p>{narrative.ariaSays}</p>
            <p className="mt-1 rounded-sm bg-surface px-1.5 py-1 font-mono text-[10px] text-text">
              {narrative.example}
            </p>
            {narrative.delayJudgment && (
              <p className="mt-1 text-[10px] text-text-muted">⚠ {narrative.delayJudgment}</p>
            )}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="w-full rounded-lg border border-border bg-bg-warm p-3">
      <div className="flex items-start gap-2">
        <Sparkles size={14} className="mt-[2px] shrink-0 text-accent" aria-hidden="true" />
        <div className="flex-1">
          <p className="text-[11px] font-medium uppercase tracking-wide text-accent">
            Aria 示範
          </p>
          <p className="mt-1 text-sm leading-relaxed text-text">{narrative.ariaSays}</p>
          <p className="mt-2 rounded-md bg-surface px-2 py-1.5 font-mono text-xs leading-relaxed text-text-muted">
            {narrative.example}
          </p>
          {narrative.delayJudgment && (
            <p className="mt-2 text-xs text-text-muted">⚠ {narrative.delayJudgment}</p>
          )}
        </div>
      </div>
    </div>
  )
}

export interface CanvasEmptyStateProps {
  stage: StartActionStage
  /** 當前 micro phase；命中時 hint 內容會深化到 micro 粒度（1.1–4.3） */
  currentMicroPhase?: MicroPhaseId | null
  visible: boolean
  onActionClick?: (actionId: string) => void
  /** 退場動畫（飛入起頭 chip 或 fade-out）完成後觸發；父層用來同步 chip flash。 */
  onHide?: () => void
}

// 退場動畫時序
const FLY_DELAY_MS = 2500
const FLY_DURATION_MS = 1400
const ANCHOR_SELECTOR = '[data-startwith-anchor]'

type ExitPhase = 'idle' | 'pending-fly' | 'flying' | 'fading'

interface FlyTransform {
  dx: number
  dy: number
  scale: number
}

export function CanvasEmptyState({
  stage,
  currentMicroPhase,
  visible,
  onActionClick,
  onHide,
}: CanvasEmptyStateProps) {
  const reducedMotion = useReducedMotion()
  const panelRef = useRef<HTMLDivElement>(null)
  const [mounted, setMounted] = useState<boolean>(visible)
  const [exitPhase, setExitPhase] = useState<ExitPhase>('idle')
  const [flyTransform, setFlyTransform] = useState<FlyTransform | null>(null)

  // 用 ref 鎖定「退場流程已啟動」，避免 setExitPhase 引發 effect 重跑時把 timer 清掉
  const exitStartedRef = useRef<boolean>(false)
  const timersRef = useRef<number[]>([])
  // onHide / reducedMotion 用 ref 取最新值，避免列在 effect deps 而觸發 cleanup
  const onHideRef = useRef(onHide)
  const reducedMotionRef = useRef(reducedMotion)
  useEffect(() => { onHideRef.current = onHide }, [onHide])
  useEffect(() => { reducedMotionRef.current = reducedMotion }, [reducedMotion])

  const clearTimers = () => {
    for (const id of timersRef.current) window.clearTimeout(id)
    timersRef.current = []
  }

  // visible → false：啟動退場流程（延遲 → 飛入 / 淡出）
  useEffect(() => {
    if (visible) {
      setMounted(true)
      setExitPhase('idle')
      setFlyTransform(null)
      exitStartedRef.current = false
      clearTimers()
      return
    }
    if (!mounted) return
    if (exitStartedRef.current) return
    exitStartedRef.current = true

    // Phase 1：延遲 FLY_DELAY_MS 讓使用者讀完起手式卡片再看第一張便利貼
    setExitPhase('pending-fly')
    const delayTimer = window.setTimeout(() => {
      const anchor = document.querySelector(ANCHOR_SELECTOR) as HTMLElement | null
      const canFly = !reducedMotionRef.current && anchor && panelRef.current

      if (!canFly) {
        // Fallback：reduced-motion 或找不到 anchor → 改用 opacity 淡出
        setExitPhase('fading')
        const fadeTimer = window.setTimeout(() => {
          setMounted(false)
          setExitPhase('idle')
          exitStartedRef.current = false
          onHideRef.current?.()
        }, EXIT_DURATION)
        timersRef.current.push(fadeTimer)
        return
      }

      // Phase 2：量測，計算 FLIP transform
      const sRect = panelRef.current!.getBoundingClientRect()
      const aRect = anchor.getBoundingClientRect()
      const sCenterX = sRect.left + sRect.width / 2
      const sCenterY = sRect.top + sRect.height / 2
      const aCenterX = aRect.left + aRect.width / 2
      const aCenterY = aRect.top + aRect.height / 2
      const dx = aCenterX - sCenterX
      const dy = aCenterY - sCenterY
      const scale = Math.max(0.08, aRect.width / Math.max(1, sRect.width))

      setFlyTransform({ dx, dy, scale })
      setExitPhase('flying')

      // Phase 3：400ms 動畫後 unmount + 通知父層
      const flyTimer = window.setTimeout(() => {
        setMounted(false)
        setExitPhase('idle')
        setFlyTransform(null)
        exitStartedRef.current = false
        onHideRef.current?.()
      }, FLY_DURATION_MS)
      timersRef.current.push(flyTimer)
    }, FLY_DELAY_MS)

    timersRef.current.push(delayTimer)
    // 注意：不在 cleanup 清 timer——只有「visible 又變 true」或 unmount 時才該清
    // visible→true 的清除在 effect 入口 clearTimers() 處理
  }, [visible, mounted])

  // 元件卸載時清掉殘留 timer
  useEffect(() => () => clearTimers(), [])

  if (!mounted) return null

  const hint = resolveStageHint(stage, currentMicroPhase)
  const stageLabel = STAGE_LABEL[stage]
  const subtitle = STAGE_SUBTITLE[stage]

  const isExiting = exitPhase !== 'idle'
  const isFlying = exitPhase === 'flying'
  const isFading = exitPhase === 'fading'
  const useStagger = !reducedMotion && !isExiting

  // 動畫期間鎖定 pointer-events 並套 transform
  const animatedStyle: React.CSSProperties = isFlying && flyTransform
    ? {
        transform: `translate(${flyTransform.dx}px, ${flyTransform.dy}px) scale(${flyTransform.scale})`,
        opacity: 0,
        transition: `transform ${FLY_DURATION_MS}ms cubic-bezier(0.4, 0, 0.2, 1), opacity ${FLY_DURATION_MS}ms cubic-bezier(0.4, 0, 0.2, 1)`,
        transformOrigin: 'center',
        pointerEvents: 'none',
        willChange: 'transform, opacity',
      }
    : isFading
      ? {
          opacity: 0,
          transition: `opacity ${EXIT_DURATION}ms`,
          pointerEvents: 'none',
        }
      : {
          opacity: 1,
          transition: `opacity ${EXIT_DURATION}ms`,
        }

  return (
    <div
      className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center px-6 py-6 overflow-auto"
      aria-hidden={!visible}
    >
      <div
        ref={panelRef}
        className="pointer-events-auto flex max-w-2xl flex-col items-center gap-5 rounded-3xl bg-white/65 px-10 py-9 shadow-[0_8px_40px_rgba(0,0,0,0.08),0_0_60px_24px_rgba(255,255,255,0.55)] backdrop-blur-xl"
        style={animatedStyle}
      >
        <div className="flex flex-col items-center gap-1 text-center">
          <span className="text-xs uppercase tracking-wide text-text-muted">
            起手式 · {stageLabel} 階段
            {currentMicroPhase ? ` · ${currentMicroPhase}` : ''}
          </span>
          <h2 className="text-lg font-semibold text-text">從這裡開始</h2>
          <p className="text-sm text-text-muted">{subtitle}</p>
        </div>

        <NarrativeHeader narrative={hint.narrative} />

        <StartActionGrid
          actions={hint.actions}
          onActionClick={onActionClick}
          animate={useStagger}
          reverseStagger={isExiting}
        />
      </div>
    </div>
  )
}

export default CanvasEmptyState
