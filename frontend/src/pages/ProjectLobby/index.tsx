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
import { SeatSelectionGrid } from './SeatSelectionGrid'
import { ObserverCard } from './ObserverCard'
import { InfoTabs } from './InfoTabs'
import type { SeatRole } from '../../types/models'

export function ProjectLobbyPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const { currentProject } = useProjectStore()
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
    (s) => s.occupant_type === 'human' && s.user_id === user?.id,
  )

  const handleJoin = async (seatRole: SeatRole) => {
    if (!id) return
    setJoinError('')
    setJoiningRole(seatRole)

    try {
      await joinProject(id, { seat_role: seatRole })
      navigate(`/projects/${id}/workspace`)
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 409) {
        setJoinError('此席位已被其他人類佔用，請選擇其他席位。')
      } else {
        setJoinError('加入失敗，請稍後再試。')
      }
    } finally {
      setJoiningRole(null)
    }
  }

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

  if (isLoading || !currentProject) {
    return <Loading fullScreen text="載入專案資訊…" />
  }

  return (
    <div className="relative pb-8">
      <LobbyHeader project={currentProject} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <SeatSelectionGrid
            seats={seats}
            currentUserId={user?.id}
            onJoin={handleJoin}
            joiningRole={joiningRole}
            joinError={joinError}
            isLocked={joiningRole !== null}
          />
        </div>
        <ObserverCard
          onEnter={handleEnterWorkspace}
          hasCurrentSeat={!!myCurrentSeat}
          isLocked={joiningRole !== null}
        />
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
