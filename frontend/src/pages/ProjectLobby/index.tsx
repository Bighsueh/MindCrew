import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { useSeatStore } from '../../stores/seatStore'
import { joinProject } from '../../services/projectService'
import { useProjectStore } from '../../stores/projectStore'
import { useLobbyData } from '../../hooks/useLobbyData'
import { Loading } from '../../components/common/Loading'
import { ScrollReveal } from '../../components/common/ScrollReveal'
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

  if (isLoading || !currentProject) {
    return <Loading fullScreen text="載入專案資訊…" />
  }

  return (
    <div className="pb-8">
      {/* Header */}
      <ScrollReveal delay={0}>
        <LobbyHeader project={currentProject} />
      </ScrollReveal>

      {/* Entry point: seats + observer side by side */}
      <ScrollReveal delay={100}>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <SeatSelectionGrid
              seats={seats}
              currentUserId={user?.id}
              onJoin={handleJoin}
              joiningRole={joiningRole}
              joinError={joinError}
            />
          </div>
          <ObserverCard
            onEnter={handleEnterWorkspace}
            hasCurrentSeat={!!myCurrentSeat}
          />
        </div>
      </ScrollReveal>

      {/* Info tabs */}
      <ScrollReveal delay={200}>
        <div className="mt-6">
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
      </ScrollReveal>
    </div>
  )
}
