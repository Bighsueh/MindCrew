import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useProjectStore } from '../../stores/projectStore'
import { useChatStore } from '../../stores/chatStore'
import { useSeatStore } from '../../stores/seatStore'
import { useStageStore } from '../../stores/stageStore'
import { useAuthStore } from '../../stores/authStore'
import { advanceStage, leaveProject, getStage } from '../../services/projectService'
import { DoubleDiamondProgress } from '../../components/progress/DoubleDiamondProgress'
import { TimerInline } from '../../components/timer/TimerInline'
import { InitTimerDialog } from '../../components/timer/InitTimerDialog'
import { useTimerStore } from '../../stores/timerStore'
import { ConnectionBanner } from '../../components/workspace/ConnectionBanner'
import { SeatBar } from '../../components/workspace/SeatBar'
import { ChatPanel } from '../../components/chat/ChatPanel'
import { ChatDock } from '../../components/chat/ChatDock'
import { CanvasPanel } from '../../components/canvas/CanvasPanel'
// Phase 19 — Dynamic AI persona panel
import { ProjectPersonasPanel } from '../../components/persona/ProjectPersonasPanel'
// Phase 20 — MindCrew-Design UI surface
import { StageHintBar } from '../../components/workspace/StageHintBar'
import {
  AdvanceStageConfirm,
  type DTStage as AdvanceDTStage,
} from '../../components/workspace/AdvanceStageConfirm'
import { StartActionsPopover } from '../../components/workspace/StartActionsPopover'
import { OnboardingModal } from '../../components/workspace/OnboardingModal'
import { Button } from '../../components/common/Button'
import { Loading } from '../../components/common/Loading'
import { HelpCircle, Users } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { ChatKind } from '../../stores/chatStore'
import type { DTStage, MicroPhaseId } from '../../types/models'
import type { StartActionStage } from '../../components/canvas/CanvasEmptyState'
import { useActivityHighlightGlobal } from '../../components/canvas/useActivityHighlightGlobal'
import { useWorkspaceWS } from './useWorkspaceWS'
import { useWorkspaceCoachState } from './useWorkspaceCoachState'
import { useStageOrchestration } from './useStageOrchestration'

// 階段推進對應表：給「推進到下一階段」按鈕使用。
const NEXT_STAGE: Partial<Record<DTStage, DTStage>> = {
  discover: 'define',
  define: 'develop',
  develop: 'deliver',
}

// 把 DTStage 收斂成 StartActionsPopover 認得的 4 階段。
function asStartActionStage(s: DTStage): StartActionStage {
  if (s === 'discover' || s === 'define' || s === 'develop' || s === 'deliver') return s
  return 'discover'
}

// mobile 三 tab 的識別字串
type MobileTab = 'canvas' | 'group' | 'personal'

export function WorkspacePage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { currentProject, fetchProject } = useProjectStore()
  const loadHistory = useChatStore((s) => s.loadHistory)
  const { seats, setSeats } = useSeatStore()
  const { currentStage, currentMicroPhase, setCurrentStage, setCurrentMicroPhase } =
    useStageStore()
  const { user } = useAuthStore()

  // Phase 24：workspace 範圍內，點空白或按 Esc → 清除 activity highlight pin
  useActivityHighlightGlobal()

  const [showAdvanceModal, setShowAdvanceModal] = useState(false)
  const [showPersonasPanel, setShowPersonasPanel] = useState(false)
  // 舊專案缺 timer_config 時，老師可從 footer 啟用倒數計時。
  const [showInitTimer, setShowInitTimer] = useState(false)
  // 「重新導引」按鈕用：遞增 nonce 強制重開 OnboardingModal
  const [onboardingForceNonce, setOnboardingForceNonce] = useState(0)
  const [isAdvancing, setIsAdvancing] = useState(false)
  const [activeTab, setActiveTab] = useState<MobileTab>('canvas')
  // 當前在前景的聊天 channel；由 ChatDock onActiveChange 回報。
  const [activeChannel, setActiveChannel] = useState<ChatKind | null>(null)

  // 衍生狀態：SeatBar 需要的 typing / preview / recentSpeaker
  const coachState = useWorkspaceCoachState({ seats })

  // Stage orchestration：banner / popover / chip flash / shapeCount
  const orchestration = useStageOrchestration({ currentStage })

  // WS：chat_id 路由 + stage / seat / micro_phase handler
  const { wsStatus, sendWS, wsError } = useWorkspaceWS({
    projectId: id,
    currentStage,
    activeChannel,
    onChatMessage: (kind, message) => {
      if (kind === 'group') coachState.markRecentSpeaker(message)
    },
  })

  // ── 載入 project 與 group 歷史 ──
  useEffect(() => {
    if (id) fetchProject(id)
  }, [id, fetchProject])

  useEffect(() => {
    if (id) loadHistory(id, 'group')
  }, [id, loadHistory])

  // ── project 載入完成 → 套用 seats / stage / microPhase ──
  useEffect(() => {
    if (currentProject) {
      if (currentProject.seats) setSeats(currentProject.seats)
      setCurrentStage(currentProject.current_stage)
      if (currentProject.current_micro_phase) {
        setCurrentMicroPhase(currentProject.current_micro_phase as MicroPhaseId)
      }
    }
  }, [currentProject, setSeats, setCurrentStage, setCurrentMicroPhase])

  // microPhase fallback：舊後端可能沒回，從 /stage 補拿。
  useEffect(() => {
    if (id && !currentMicroPhase) {
      getStage(id)
        .then((stageInfo) => {
          if (stageInfo.current_micro_phase) {
            setCurrentMicroPhase(stageInfo.current_micro_phase as MicroPhaseId)
          }
        })
        .catch(() => {
          /* ignore — old backend may not support this */
        })
    }
  }, [id, currentMicroPhase, setCurrentMicroPhase])

  // ── 權限與存取控管 ──
  const myCurrentSeat = seats.find(
    (s) => s.occupant_type === 'human' && s.user_id === user?.id,
  )
  const isObserver = !myCurrentSeat
  const isSupervisor = myCurrentSeat?.seat_role === 'supervisor'
  const nextStage = NEXT_STAGE[currentStage]

  const hasAccess =
    currentProject &&
    user &&
    (currentProject.creator_id === user.id ||
      currentProject.seats?.some((s) => s.user_id === user.id) ||
      user.role === 'teacher')

  useEffect(() => {
    if (currentProject && user && !hasAccess) {
      navigate(`/projects/${id}/lobby`, { replace: true })
    }
  }, [currentProject, user, hasAccess, id, navigate])

  // ── 推進階段 ──
  const handleAdvanceStage = useCallback(async () => {
    if (!id || !nextStage) return
    setIsAdvancing(true)
    try {
      await advanceStage(id, { from: currentStage, to: nextStage })
      setCurrentStage(nextStage)
      setShowAdvanceModal(false)
    } catch {
      // ignore — WS 會廣播階段變更
    } finally {
      setIsAdvancing(false)
    }
  }, [id, nextStage, currentStage, setCurrentStage])

  const handleLeave = useCallback(async () => {
    if (!id) return
    try {
      await leaveProject(id)
    } finally {
      navigate(`/projects/${id}/lobby`)
    }
  }, [id, navigate])

  // ── EmptyState 動作 ──
  // 任一動作目前皆為「閃 chip + 關 popover」的 UX placeholder；後續 phase 才接入實際後端流程。
  const handleEmptyStateAction = useCallback(
    (_actionId: string) => {
      orchestration.flashStartChip()
      orchestration.closeStartPopover()
    },
    [orchestration],
  )

  const handleStartChipClick = useCallback(() => {
    orchestration.toggleStartPopover()
  }, [orchestration])

  // ── EmptyState banner 是否顯示（CanvasPanel 用） ──
  const bannerVisible = useMemo(
    () =>
      !orchestration.bannerDismissedStages.has(currentStage) &&
      orchestration.shapeCount === 0,
    [orchestration.bannerDismissedStages, orchestration.shapeCount, currentStage],
  )

  const handleShapeCountChange = useCallback(
    (count: number) => {
      orchestration.setShapeCount(count)
      // 第一張便利貼出現 → bannerVisible 變 false → CanvasEmptyState 啟動退場動畫
      // chip flash 改由 onEmptyStateHide 在飛入動畫抵達時觸發（視覺同步）
    },
    [orchestration],
  )

  if (!currentProject) {
    return <Loading fullScreen text="載入工作區…" />
  }

  if (!hasAccess) {
    return <Loading fullScreen text="正在跳轉至大廳…" />
  }

  const showBanner = wsStatus === 'disconnected' || wsStatus === 'failed' || wsError
  const startStage = asStartActionStage(currentStage)

  return (
    <div className="flex h-screen flex-col bg-bg overflow-hidden">
      {/* WS disconnect banner */}
      {showBanner && (
        <ConnectionBanner status={wsStatus === 'failed' ? 'failed' : 'disconnected'} />
      )}

      {/* DT Progress bar + 全員 Timer（specs/16-timer-system.md §6.5.3） */}
      <header className="flex-shrink-0 border-b border-border bg-surface px-4 py-2">
        <div className="flex items-center gap-4">
          <span className="text-sm text-text-muted whitespace-nowrap">
            {currentProject.name}
          </span>
          <div className="flex-1 min-w-0 flex justify-center">
            <DoubleDiamondProgress
              currentStage={currentStage}
              currentMicroPhase={currentMicroPhase ?? undefined}
            />
          </div>
          <button
            type="button"
            onClick={() => setOnboardingForceNonce((n) => n + 1)}
            aria-label="重新導引"
            title="重新導引"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-text-muted hover:bg-surface-hover hover:text-text transition-colors"
          >
            <HelpCircle size={16} />
          </button>
        </div>
      </header>

      {/* Stage hint bar：目標、任務、起頭 chip */}
      <StageHintBar
        stage={currentStage}
        projectId={id!}
        currentMicroPhase={currentMicroPhase}
        onStartWithAiClick={handleStartChipClick}
        startChipFlashKey={orchestration.startChipFlashKey}
      />

      {/* Main content area */}
      <div className="relative flex-1 overflow-hidden">
        {/* Mobile: 三 tab（白板 / 群組聊天室 / 個人助理） */}
        <div className="flex md:hidden flex-col h-full overflow-hidden">
          <div className="flex border-b border-border bg-surface">
            <MobileTabButton
              active={activeTab === 'canvas'}
              onClick={() => setActiveTab('canvas')}
              label="白板"
            />
            <MobileTabButton
              active={activeTab === 'group'}
              onClick={() => setActiveTab('group')}
              label="群組聊天室"
            />
            <MobileTabButton
              active={activeTab === 'personal'}
              onClick={() => setActiveTab('personal')}
              label="個人助理"
            />
          </div>
          <div className="flex-1 overflow-hidden">
            {activeTab === 'canvas' && (
              <div className="h-full">
                <CanvasPanel
                  projectId={id!}
                  currentStage={currentStage}
                  currentMicroPhase={currentMicroPhase}
                  emptyStateVisible={bannerVisible}
                  onShapeCountChange={handleShapeCountChange}
                  onEmptyStateAction={handleEmptyStateAction}
                  onEmptyStateHide={orchestration.flashStartChip}
                  isObserver={isObserver}
                />
              </div>
            )}
            {activeTab === 'group' && (
              <ChatPanel
                projectId={id!}
                sendWS={sendWS}
                kind="group"
                disabled={isObserver}
              />
            )}
            {activeTab === 'personal' && user && (
              <ChatPanel
                projectId={id!}
                sendWS={sendWS}
                kind="personal"
                chatId={`${id}:personal:${user.id}`}
                title="個人助理"
                inputPlaceholder="與個人助理對話…"
              />
            )}
          </div>
        </div>

        {/* Tablet/Desktop：全寬 canvas + ChatDock 浮動聊天 */}
        <div className="hidden md:block h-full relative overflow-hidden">
          <div className="h-full">
            <CanvasPanel
              projectId={id!}
              currentStage={currentStage}
              currentMicroPhase={currentMicroPhase}
              emptyStateVisible={bannerVisible}
              onShapeCountChange={handleShapeCountChange}
              onEmptyStateAction={handleEmptyStateAction}
              onEmptyStateHide={orchestration.flashStartChip}
              isObserver={isObserver}
            />
          </div>

          {user && (
            <ChatDock
              projectId={id!}
              currentUserId={user.id}
              sendWS={sendWS}
              initialOpen="group"
              groupDisabled={isObserver}
              onActiveChange={setActiveChannel}
            />
          )}
        </div>
      </div>

      {/* Seat status bar + 全員 Timer（specs/16-timer-system.md §6.5.3）。
          三段式 layout：SeatBar 左 / TimerInline 居中 / 操作鈕右。
          overflow-x-visible 避免 SeatPopover 被裁切（spec §6 trade-off）。 */}
      <footer className="flex-shrink-0 border-t border-border bg-surface px-4 py-2">
        <div className="flex items-center gap-3 overflow-x-visible">
          <div className="flex-1 min-w-0">
            <SeatBar
              seats={seats}
              currentUserId={user?.id}
              typingNames={coachState.typingNames}
              recentSpeaker={coachState.recentSpeaker}
              seatPreviews={coachState.seatPreviews}
            />
          </div>

          <TimerInline
            isCreator={currentProject?.creator_id === user?.id}
            onActivate={() => setShowInitTimer(true)}
          />

          <div className="flex-1 flex justify-end items-center gap-2">
            {currentProject?.creator_id === user?.id && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowPersonasPanel(true)}
              >
                <Users size={14} />
                AI 隊友
              </Button>
            )}
            {isSupervisor && nextStage && (
              <Button size="sm" onClick={() => setShowAdvanceModal(true)}>
                推進到 {nextStage}
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={handleLeave}>
              離開
            </Button>
          </div>
        </div>
      </footer>

      {/* Phase 20: Advance stage confirmation (replaces old Modal-based UI from Phase 19) */}
      <AdvanceStageConfirm
        open={showAdvanceModal}
        currentStage={
          (currentStage === 'completed' ? 'deliver' : currentStage) as AdvanceDTStage
        }
        onConfirm={handleAdvanceStage}
        onCancel={() => setShowAdvanceModal(false)}
        isAdvancing={isAdvancing}
      />

      {/* Phase 20: 起手式 popover, anchored on the StageHintBar 「起頭」chip */}
      <StartActionsPopover
        open={orchestration.startPopoverOpen}
        stage={startStage}
        currentMicroPhase={currentMicroPhase}
        anchorSelector="[data-startwith-anchor]"
        onActionClick={handleEmptyStateAction}
        onClose={orchestration.closeStartPopover}
      />

      {/* 新手導引 Modal：首次進入專案自動跳出；右上角 ? icon 可重開 */}
      <OnboardingModal
        projectId={id!}
        project={currentProject}
        forceOpenNonce={onboardingForceNonce}
      />


      {/* Phase 19: AI persona management (creator only) */}
      {showPersonasPanel && currentProject && (
        <ProjectPersonasPanel
          isOpen={showPersonasPanel}
          projectId={currentProject.id}
          seats={seats}
          onClose={() => setShowPersonasPanel(false)}
          onUpdated={(updatedSeat) => updateSeat(updatedSeat.seat_role, updatedSeat)}
        />
      )}

      {/* 舊專案啟用 timer（specs/16-timer-system.md） */}
      {id && (
        <InitTimerDialog
          isOpen={showInitTimer}
          projectId={id}
          onClose={() => setShowInitTimer(false)}
          onInitialized={() => {
            setShowInitTimer(false)
            // 立即把 store 標 available=true 讓 footer 馬上反應；
            // useProjectRealtime 5s polling 會接著用真實 budget/used_seconds 蓋過。
            useTimerStore.getState().setSnapshot({
              available: true,
              current_sub_phase: '1.1a',
              paused: false,
            })
          }}
        />
      )}
    </div>
  )
}

interface MobileTabButtonProps {
  active: boolean
  onClick: () => void
  label: string
}

function MobileTabButton({ active, onClick, label }: MobileTabButtonProps) {
  return (
    <button
      className={cn(
        'flex-1 py-2 text-sm font-medium border-b-2 transition-colors',
        active
          ? 'border-accent text-accent'
          : 'border-transparent text-text-muted',
      )}
      onClick={onClick}
    >
      {label}
    </button>
  )
}
