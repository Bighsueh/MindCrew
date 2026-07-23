// Workspace 新手導引 Modal
// 四個 step（第 4 步含「開始」CTA），引導使用者理解：
//   歡迎 → 設計思考概念 + 第一鑽石流程 → 三階段說明 + 雙工具與「你的任務」 → 主題/限制/行動指引

import { useEffect, useState } from 'react'
import { ChevronRight, ChevronLeft, ExternalLink } from 'lucide-react'
import { Modal } from '../common/Modal'
import { useFirstRunFlag } from '../../hooks/useFirstRunFlag'
import { DoubleDiamondDiagram } from './DoubleDiamondDiagram'
import {
  ONBOARDING_LEAD_IN,
  DT_DEFINITION,
  DOUBLE_DIAMOND_NARRATIVE,
  PHASE_DESCRIPTIONS,
  COLLAB_NOTE,
  DUAL_TOOL_NOTE,
  TASK_BANNER_NOTE,
  STAGE_NEXT_HINT,
  STAGE_HEADING_LABEL,
} from './onboardingContent'
import type { Project, DTStage } from '../../types/models'

export interface OnboardingModalProps {
  projectId: string
  project: Pick<Project, 'name' | 'description' | 'constraints' | 'current_stage'> | null
  /** 手動觸發開啟（給「重新導引」按鈕用）；變化即重新開啟並重設 step。 */
  forceOpenNonce?: number
  /** 點「前往設定」時呼叫，由父層負責導向專案設定頁；未提供則只顯示連結文字。 */
  onGoToSettings?: () => void
}

const TOTAL_STEPS = 4

export function OnboardingModal({
  projectId,
  project,
  forceOpenNonce,
  onGoToSettings,
}: OnboardingModalProps) {
  const [shouldShow, dismiss] = useFirstRunFlag(`onboarding-modal-${projectId}`)
  const [isOpen, setIsOpen] = useState<boolean>(shouldShow)
  const [step, setStep] = useState<number>(1)

  useEffect(() => {
    if (shouldShow) setIsOpen(true)
  }, [shouldShow])

  // 父層遞增 nonce → 強制重開（已關掉時也能再開）
  useEffect(() => {
    if (forceOpenNonce === undefined) return
    if (forceOpenNonce <= 0) return
    setStep(1)
    setIsOpen(true)
  }, [forceOpenNonce])

  if (!project) return null

  const close = () => {
    dismiss()
    setIsOpen(false)
  }

  const next = () => setStep((s) => Math.min(TOTAL_STEPS, s + 1))
  const prev = () => setStep((s) => Math.max(1, s - 1))

  return (
    <Modal isOpen={isOpen} onClose={close} maxWidth="2xl">
      <div className="flex flex-col gap-5">
        <StepIndicator current={step} total={TOTAL_STEPS} />

        {step === 1 && <StepWelcome projectName={project.name} />}
        {step === 2 && <StepConcept />}
        {step === 3 && <StepMore />}
        {step === 4 && (
          <StepBriefing
            project={project}
            stage={project.current_stage}
            onGoToSettings={onGoToSettings}
          />
        )}

        <NavBar
          step={step}
          total={TOTAL_STEPS}
          onPrev={prev}
          onNext={next}
          onFinish={close}
        />
      </div>
    </Modal>
  )
}

// ── Step Indicator ─────────────────────────────────────────────────────────

interface StepIndicatorProps {
  current: number
  total: number
}

function StepIndicator({ current, total }: StepIndicatorProps) {
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: total }, (_, i) => i + 1).map((i) => (
        <span
          key={i}
          className={
            i === current
              ? 'h-1.5 flex-1 rounded-full bg-accent transition-colors'
              : i < current
              ? 'h-1.5 flex-1 rounded-full bg-accent/40 transition-colors'
              : 'h-1.5 flex-1 rounded-full bg-border transition-colors'
          }
          aria-current={i === current ? 'step' : undefined}
        />
      ))}
    </div>
  )
}

// ── Step 1: Welcome ────────────────────────────────────────────────────────

function StepWelcome({ projectName }: { projectName: string }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs font-medium uppercase tracking-wide text-accent">Step 1 · 歡迎</p>
      <h2 className="text-2xl font-semibold text-text">
        歡迎來到「{projectName}」的設計思考活動
      </h2>
      <p className="text-sm leading-relaxed text-text-muted">{ONBOARDING_LEAD_IN}</p>
    </div>
  )
}

// ── Step 2: DT 概念 + 設計思考流程 ─────────────────────────────────────────

function StepConcept() {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs font-medium uppercase tracking-wide text-accent">Step 2 · 概念與流程</p>
      <h2 className="text-xl font-semibold text-text">什麼是設計思考？</h2>
      <p className="text-sm leading-relaxed text-text-muted">{DT_DEFINITION}</p>
      <div className="rounded-lg border border-border bg-bg-warm p-3">
        <DoubleDiamondDiagram />
      </div>
      <ul className="flex flex-col gap-1.5 text-xs leading-relaxed text-text-muted">
        {DOUBLE_DIAMOND_NARRATIVE.map((line) => (
          <li key={line} className="flex gap-1.5">
            <span className="text-accent">·</span>
            <span>{line}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ── Step 3: 三階段說明 + 雙工具與「你的任務」 ─────────────────────────────────

function StepMore() {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs font-medium uppercase tracking-wide text-accent">Step 3 · 更多說明</p>
      <h2 className="text-xl font-semibold text-text">這場活動會這樣一步步進行</h2>
      <div className="flex flex-col gap-2">
        {PHASE_DESCRIPTIONS.map((phase) => (
          <div
            key={phase.id}
            className="flex flex-col gap-1 rounded-md border border-border bg-surface px-3 py-2"
          >
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-text">{phase.label}</span>
              <span className="rounded-sm bg-accent/10 px-1.5 py-[1px] text-[10px] font-medium text-accent">
                {phase.shape}
              </span>
            </div>
            <p className="text-xs leading-relaxed text-text-muted">{phase.body}</p>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-2">
        <p className="rounded-md border border-border bg-bg-warm px-3 py-2 text-xs text-text-muted">
          💡 {COLLAB_NOTE}
        </p>
        <p className="rounded-md border border-border bg-bg-warm px-3 py-2 text-xs text-text-muted">
          🧰 {DUAL_TOOL_NOTE}
        </p>
        <p className="rounded-md border border-accent/40 bg-accent/5 px-3 py-2 text-xs text-text-muted">
          📌 {TASK_BANNER_NOTE}
        </p>
      </div>
    </div>
  )
}

// ── Step 4: 主題 + 限制 + 行動指引 ─────────────────────────────────────────

interface StepBriefingProps {
  project: Pick<Project, 'name' | 'description' | 'constraints'>
  stage: DTStage
  onGoToSettings?: () => void
}

function StepBriefing({ project, stage, onGoToSettings }: StepBriefingProps) {
  const description = project.description?.trim()
  const constraints = project.constraints?.trim()
  const stageLabel = STAGE_HEADING_LABEL[stage] ?? stage
  const nextHint = STAGE_NEXT_HINT[stage] ?? ''

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs font-medium uppercase tracking-wide text-accent">Step 4 · 本場簡報</p>
      <h2 className="text-xl font-semibold text-text">本場活動的主題與限制</h2>

      <BriefingField label="主題" value={description} onGoToSettings={onGoToSettings} />
      <BriefingField label="限制條件" value={constraints} onGoToSettings={onGoToSettings} />

      <div className="rounded-lg border border-accent/40 bg-accent/5 p-3">
        <p className="text-xs font-medium uppercase tracking-wide text-accent">
          你目前在 {stageLabel}
        </p>
        <p className="mt-1 text-sm leading-relaxed text-text">{nextHint}</p>
      </div>
    </div>
  )
}

interface BriefingFieldProps {
  label: string
  value?: string
  onGoToSettings?: () => void
}

function BriefingField({ label, value, onGoToSettings }: BriefingFieldProps) {
  const hasValue = Boolean(value && value.length > 0)
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2">
      <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">{label}</p>
      {hasValue ? (
        <p className="mt-1 text-sm leading-relaxed text-text whitespace-pre-wrap">{value}</p>
      ) : (
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <span className="text-sm text-text-muted">尚未設定</span>
          {onGoToSettings && (
            <button
              type="button"
              onClick={onGoToSettings}
              className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
            >
              前往活動設定補上 <ExternalLink size={12} />
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ── Navigation ─────────────────────────────────────────────────────────────

interface NavBarProps {
  step: number
  total: number
  onPrev: () => void
  onNext: () => void
  onFinish: () => void
}

function NavBar({ step, total, onPrev, onNext, onFinish }: NavBarProps) {
  const isFirst = step === 1
  const isLast = step === total
  return (
    <div className="mt-2 flex items-center justify-between border-t border-border pt-4">
      <button
        type="button"
        onClick={onPrev}
        disabled={isFirst}
        className="inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-sm text-text-muted hover:bg-surface-hover hover:text-text disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
      >
        <ChevronLeft size={14} />
        上一步
      </button>
      <span className="text-xs text-text-muted">
        {step} / {total}
      </span>
      {isLast ? (
        <button
          type="button"
          onClick={onFinish}
          className="inline-flex items-center gap-1 rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-text-inverse hover:bg-accent/90"
        >
          開始
        </button>
      ) : (
        <button
          type="button"
          onClick={onNext}
          className="inline-flex items-center gap-1 rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-text-inverse hover:bg-accent/90"
        >
          下一步
          <ChevronRight size={14} />
        </button>
      )}
    </div>
  )
}

export default OnboardingModal
