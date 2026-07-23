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
import { RoomPausedBanner } from '../../components/workspace/RoomPausedBanner'
import { ChatPanel } from '../../components/chat/ChatPanel'
import { ChatDock } from '../../components/chat/ChatDock'
import { CanvasPanel } from '../../components/canvas/CanvasPanel'
// Phase 20 — MindCrew-Design UI surface
import { TaskBanner } from '../../components/workspace/TaskBanner'
import { WaitingIndicator } from '../../components/workspace/WaitingIndicator'
import { InputBouncedToast } from '../../components/workspace/InputBouncedToast'
import { TurnPolicySwitcher } from '../../components/teacher/TurnPolicySwitcher'
import { AdvanceStageConfirm } from '../../components/workspace/AdvanceStageConfirm'
import type { DTStage as AdvanceDTStage } from '../../types/models'
import { OnboardingModal } from '../../components/workspace/OnboardingModal'
import { Button } from '../../components/common/Button'
import { Loading } from '../../components/common/Loading'
import { HelpCircle } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { ChatKind } from '../../stores/chatStore'
import type { DTStage, MicroPhaseId } from '../../types/models'
import { useActivityHighlightGlobal } from '../../components/canvas/useActivityHighlightGlobal'
import { useTimerTick } from '../../hooks/useTimerTick'
import { useWorkspaceWS } from './useWorkspaceWS'
import { useWorkspaceCoachState } from './useWorkspaceCoachState'
import { useStageOrchestration } from './useStageOrchestration'

// 階段推進對應表：給「推進到下一階段」按鈕使用。
// Phase 29 (spec/04-06 §4.10): develop / deliver removed; define 後直接 completed。
const NEXT_STAGE: Partial<Record<DTStage, DTStage>> = {
  warmup: 'discover',
  discover: 'define',
  define: 'completed',
}

// mobile 三 tab 的識別字串
type MobileTab = 'canvas' | 'group' | 'personal'

export function WorkspacePage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { currentProject, fetchProject } = useProjectStore()
  const loadHistory = useChatStore((s) => s.loadHistory)
  const { seats, setSeats, updateSeat } = useSeatStore()
  const { currentStage, currentMicroPhase, setCurrentStage, setCurrentMicroPhase } =
    useStageStore()
  const { user } = useAuthStore()

  // Phase 24：workspace 範圍內，點空白或按 Esc → 清除 activity highlight pin
  useActivityHighlightGlobal()

  // 計時器每秒本地遞減的單一計時源（只在此掛一次；TimerInline 被響應式雙掛，
  // 不可由元件自身計時，否則 used_seconds 每秒 +2 造成倒數抖動）。
  useTimerTick()

  const [showAdvanceModal, setShowAdvanceModal] = useState(false)
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
    (s) => s.occupant_type === 'human' && !!s.user_id && s.user_id === user?.id,
  )
  const isObserver = !myCurrentSeat
  const isSupervisor = myCurrentSeat?.seat_role === 'supervisor'
  const nextStage = NEXT_STAGE[currentStage]

  // 存取：creator（含 viewer_role==='creator'）/ 列管老師 / admin 才可進工作區。
  // 收斂掉舊版「任何 teacher 皆可」的寬鬆判斷。
  const hasAccess =
    !!currentProject &&
    !!user &&
    (currentProject.viewer_role != null ||
      currentProject.creator_id === user.id ||
      currentProject.linked_teacher?.id === user.id ||
      user.role === 'admin')

  // Phase 28：教師且為本專案 linked_teacher，或 admin，可在 Workspace 即時切換 turn_policy
  const canManageTurnPolicy = !!(
    currentProject &&
    user &&
    (user.role === 'admin' ||
      (user.role === 'teacher' && currentProject.linked_teacher?.id === user.id))
  )

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
  // 任一動作目前皆為「閃 chip」的 UX placeholder；後續 phase 才接入實際後端流程。
  const handleEmptyStateAction = useCallback(
    (_actionId: string) => {
      orchestration.flashStartChip()
    },
    [orchestration],
  )

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

  return (
    <div className="flex h-screen flex-col bg-bg overflow-hidden">
      {/* WS disconnect banner */}
      {showBanner && (
        <ConnectionBanner status={wsStatus === 'failed' ? 'failed' : 'disconnected'} />
      )}

      {/* Phase 42 D5：LLM fail-stop 全房暫停 banner（room_paused/room_resumed 驅動）。 */}
      <RoomPausedBanner />

      {/* DT Progress bar + 全員 Timer（） */}
      <header className="flex-shrink-0 border-b border-border bg-surface px-4 py-2">
        <div className="flex items-center gap-4">
          <span className="text-sm text-text-muted whitespace-nowrap shrink-0">
            {currentProject.name}
          </span>
          <div className="flex-1 min-w-0 flex justify-center">
            <DoubleDiamondProgress
              currentStage={currentStage}
              currentMicroPhase={currentMicroPhase ?? undefined}
            />
          </div>

          {/* 右側叢集：只留操作鈕。
              在席座位 chip 已移除——隊友改由聊天室的臉堆 + 資料卡呈現，navbar 不再重複。 */}
          <div className="flex items-center gap-2 shrink-0">
            {/* 操作鈕：推進 / 離開 */}
            {isSupervisor && nextStage && (
              <Button size="sm" onClick={() => setShowAdvanceModal(true)}>
                推進到 {nextStage}
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={handleLeave}>
              離開
            </Button>

            {/* Phase 28：教師 / admin 可在 Workspace 內即時切換 turn_policy。
                學生看不到（保持輪流條件對學生透明）。 */}
            {canManageTurnPolicy && (
              <TurnPolicySwitcher
                projectId={currentProject.id}
                projectName={currentProject.name}
                currentPolicy={currentProject.turn_policy ?? 'cued'}
                compact
                className="shrink-0"
              />
            )}
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
        </div>
      </header>

      {/* Phase 42 A3（WP7）：「你的任務」釘住 banner ＋ 回合鎖等待狀態列 ＋ 退回 toast。
          釘在聊天/白板上方、非聊天流訊息——洗版不消失（spec 05 Flow 4/Flow 12，#24）。 */}
      <TaskBanner
        sendWS={sendWS}
        isHumanParticipant={!isObserver && currentProject?.creator_id === user?.id}
      />
      <WaitingIndicator />
      <InputBouncedToast />

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
              <div className="relative h-full">
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
                {/* mobile：timer 也改浮動置頂（縮小可捲動） */}
                <div className="pointer-events-none absolute top-2 left-0 right-0 z-30 flex justify-center px-2">
                  <div className="pointer-events-auto max-w-full overflow-x-auto">
                    <TimerInline
                      isCreator={currentProject?.creator_id === user?.id}
                      onActivate={() => setShowInitTimer(true)}
                    />
                  </div>
                </div>
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

          {/* 倒數計時器：原 footer 中央的大 timer，改成白板頂部置中的浮動 HUD，
              讓老師遠看也清楚；白板底部已有 MiniToolbar / ChatDock，故置頂不衝突。 */}
          <div className="pointer-events-none absolute top-3 left-1/2 z-30 -translate-x-1/2">
            <div className="pointer-events-auto">
              <TimerInline
                isCreator={currentProject?.creator_id === user?.id}
                onActivate={() => setShowInitTimer(true)}
              />
            </div>
          </div>

          {user && (
            <ChatDock
              projectId={id!}
              currentUserId={user.id}
              sendWS={sendWS}
              initialOpen="group"
              groupDisabled={isObserver}
              onActiveChange={setActiveChannel}
              isCreator={currentProject?.creator_id === user?.id}
              onPersonaSaved={(seat) => updateSeat(seat.seat_role, seat)}
            />
          )}
        </div>
      </div>

      {/* footer 已移除：在席狀態 + 操作鈕上移到 header app bar；
          全員 Timer 改成白板頂部置中的浮動 HUD。 */}

      {/* Phase 20: Advance stage confirmation (replaces old Modal-based UI from Phase 19) */}
      <AdvanceStageConfirm
        open={showAdvanceModal}
        // Phase 29: completed is terminal — display as define for confirm modal heading
        currentStage={
          (currentStage === 'completed' ? 'define' : currentStage) as AdvanceDTStage
        }
        onConfirm={handleAdvanceStage}
        onCancel={() => setShowAdvanceModal(false)}
        isAdvancing={isAdvancing}
      />

      {/* 新手導引 Modal：首次進入專案自動跳出；右上角 ? icon 可重開 */}
      <OnboardingModal
        projectId={id!}
        project={currentProject}
        forceOpenNonce={onboardingForceNonce}
      />


      {/* Phase 19 的「AI 隊友人設」面板已下架：改由 SeatPopover 就地編輯（建立者點 AI 座位卡）。 */}

      {/* 舊專案啟用 timer（） */}
      {id && (
        <InitTimerDialog
          isOpen={showInitTimer}
          projectId={id}
          onClose={() => setShowInitTimer(false)}
          onInitialized={() => {
            setShowInitTimer(false)
            // 立即把 store 標 available=true 讓 footer 馬上反應；current_sub_phase 不寫死
            // （新專案是從暖場 0.0a 開始、非 1.1a；寫死會短暫顯示錯代號），交給
            // useProjectRealtime 5s polling 帶回真實 sub_phase + 友善 label。
            useTimerStore.getState().setSnapshot({
              available: true,
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
