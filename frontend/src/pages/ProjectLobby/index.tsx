import { useState, useRef, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ChevronDown } from 'lucide-react'
import { useAuthStore } from '../../stores/authStore'
import { useSeatStore } from '../../stores/seatStore'
import { joinProject } from '../../services/projectService'
import { useProjectStore } from '../../stores/projectStore'
import { useLobbyData } from '../../hooks/useLobbyData'
import { Loading } from '../../components/common/Loading'
import { LobbyHeader } from './LobbyHeader'
import { WorkshopInfoCard } from './WorkshopInfoCard'
import { SeatSelectionGrid } from './SeatSelectionGrid'
import { ObserverCard } from './ObserverCard'
import { JoinSeatCard } from './JoinSeatCard'
import { InfoTabs } from './InfoTabs'
import { StakeholderPanel } from './StakeholderPanel'
import type { SeatRole } from '../../types/models'

export function ProjectLobbyPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const {
    currentProject,
    isLoading: projectLoading,
    error: projectError,
    errorStatus,
  } = useProjectStore()
  const { seats } = useSeatStore()

  const {
    recentMessages,
    typingUsers,
    stageInfo,
    stageHistory,
    canvasState,
    wsStatus,
    isLoading,
    messageCount,
  } = useLobbyData(id)

  const [joiningRole, setJoiningRole] = useState<SeatRole | null>(null)
  const [joinError, setJoinError] = useState('')

  const myCurrentSeat = seats.find(
    (s) =>
      s.occupant_type === 'human' &&
      !!s.user_id &&
      s.user_id === user?.id,
  )

  const handleJoin = async (seatRole: SeatRole) => {
    if (!id) return
    setJoinError('')
    setJoiningRole(seatRole)

    try {
      await joinProject(id, { seat_role: seatRole })
      navigate(`/projects/${id}/workspace`)
    } catch (err: unknown) {
      const errObj = err as {
        response?: { status?: number; data?: { detail?: string } }
      }
      const status = errObj?.response?.status
      const detail = errObj?.response?.data?.detail ?? ''
      if (status === 409) {
        if (detail.includes('already has a human participant')) {
          setJoinError('此設計專案已有人類參與者。')
        } else if (detail.includes('already occupy')) {
          setJoinError('你已經在這個設計專案中佔有一個席位。')
        } else {
          setJoinError('此席位已被其他人類佔用，請選擇其他席位。')
        }
      } else {
        setJoinError('加入失敗，請稍後再試。')
      }
    } finally {
      setJoiningRole(null)
    }
  }

  // viewer_role 由後端依 current_user 計算（creator 可入座 / observer 旁觀 / null 無權）。
  // 後備：若欄位缺漏，以 creator_id 比對推斷。
  const viewerRole: 'creator' | 'observer' | null =
    currentProject?.viewer_role ??
    (currentProject?.creator_id === user?.id ? 'creator' : null)
  const isCreator = viewerRole === 'creator'
  const isObserverView = viewerRole === 'observer'

  // 唯一可入座席 = 空置的真人專屬席（綁 creator）。
  const humanSeat = seats.find((s) => s.seat_role === 'human_creator')
  const humanSeatVacant = !!humanSeat && !humanSeat.user_id
  const humanSeatRole = (humanSeat?.seat_role ?? 'human_creator') as SeatRole

  // 真人席被「別人」佔走（理論上不會，因只有 creator 能入座）。
  const projectHasHuman = seats.some(
    (s) => s.occupant_type === 'human' && !!s.user_id,
  )

  const handleEnterWorkspace = () => {
    navigate(`/projects/${id}/workspace`)
  }

  const infoTabsRef = useRef<HTMLDivElement>(null)
  const [showScrollHint, setShowScrollHint] = useState(false)

  useEffect(() => {
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (prefersReduced) return

    const el = infoTabsRef.current
    if (!el) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShowScrollHint(false)
          observer.disconnect()
        } else {
          setShowScrollHint(true)
        }
      },
      { threshold: 0.05 },
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [isLoading])

  const scrollToInfoTabs = useCallback(() => {
    infoTabsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  // 載入失敗（403 無權 / 404 不存在 / 其他）→ 導回專案列表並帶提示，
  // 避免過去「沒權限卻無限轉圈」的死路（403 不像 401，不會被攔截器導回登入）。
  useEffect(() => {
    if (projectLoading || currentProject || !projectError) return
    const notice =
      errorStatus === 403
        ? '你沒有這個專案的存取權，已為你返回專案列表。'
        : errorStatus === 404
          ? '找不到這個專案，可能已被刪除。'
          : '載入專案失敗，請稍後再試。'
    // 用 sessionStorage 傳遞一次性提示，避免 react-router location.state 在
    // 導向後的 render 時序/重掛載中遺失；Projects 頁讀取後即清除。
    sessionStorage.setItem('mc_redirect_notice', notice)
    navigate('/projects', { replace: true })
  }, [projectLoading, currentProject, projectError, errorStatus, navigate])

  // 失敗待導向期間不顯示載入動畫（否則仍像卡住）；交由上面的 effect 導回。
  if (projectError && !currentProject && !projectLoading) {
    return null
  }

  if (isLoading || !currentProject) {
    return <Loading fullScreen text="載入活動資訊…" />
  }

  return (
    <div className="relative mx-auto max-w-6xl pb-8">
      <LobbyHeader project={currentProject} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 lg:items-start">
        {/* 左欄：脈絡（工作坊資訊 → 設計團隊 → 利害關係人） */}
        <div className="space-y-6 lg:col-span-2">
          <WorkshopInfoCard project={currentProject} />
          <SeatSelectionGrid
            seats={seats}
            currentUserId={user?.id}
            viewerRole={viewerRole}
          />
          <StakeholderPanel stakeholders={currentProject.stakeholders ?? []} />
        </div>

        {/* 右欄：行動卡（sticky 跟隨捲動，CTA 永遠在視線內） */}
        <div className="lg:sticky lg:top-6">
          {isCreator ? (
            <JoinSeatCard
              onJoin={() => handleJoin(humanSeatRole)}
              onEnter={handleEnterWorkspace}
              hasCurrentSeat={!!myCurrentSeat}
              canJoin={humanSeatVacant}
              isLocked={joiningRole !== null}
              projectFull={projectHasHuman && !myCurrentSeat}
              joinError={joinError}
            />
          ) : (
            <ObserverCard
              onEnter={handleEnterWorkspace}
              hasCurrentSeat={!!myCurrentSeat}
              isLocked={joiningRole !== null}
              canObserve={isObserverView}
            />
          )}
        </div>
      </div>

      <div ref={infoTabsRef} className="mt-6">
        <InfoTabs
          messages={recentMessages}
          typingUsers={typingUsers}
          wsStatus={wsStatus}
          stageInfo={stageInfo}
          stageHistory={stageHistory}
          messageCount={messageCount}
          noteCount={canvasState?.total_notes ?? 0}
          aiContribution={currentProject.ai_contribution}
          canvasState={canvasState}
          projectId={id!}
        />
      </div>

      {showScrollHint && (
        <button
          type="button"
          onClick={scrollToInfoTabs}
          aria-label="捲動查看更多資訊"
          className="sticky bottom-0 left-0 right-0 z-10 flex w-full cursor-pointer flex-col items-center gap-1 bg-gradient-to-t from-bg via-bg/60 to-transparent pb-3 pt-10 transition-opacity duration-500"
        >
          <span className="text-xs font-medium text-text-muted">更多資訊</span>
          <ChevronDown size={18} className="animate-bounce-gentle text-text-muted" />
        </button>
      )}

      {joiningRole && <Loading fullScreen text="準備進入工作區…" />}
    </div>
  )
}
