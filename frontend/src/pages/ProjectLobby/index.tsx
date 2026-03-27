import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useProjectStore } from '../../stores/projectStore'
import { useSeatStore } from '../../stores/seatStore'
import { useAuthStore } from '../../stores/authStore'
import { joinProject } from '../../services/projectService'
import { Button } from '../../components/common/Button'
import { Loading } from '../../components/common/Loading'
import { PhaseIndicator } from '../../components/common/PhaseIndicator'
import { SeatBar } from '../../components/workspace/SeatBar'
import { ChevronLeft, Bot, User } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { SeatRole } from '../../types/models'

const AI_LABELS = {
  low: '低',
  medium: '中',
  high: '高',
}

const SEAT_ROLE_LABELS: Record<string, string> = {
  supervisor: 'Supervisor',
  crew_1: 'Crew 1',
  crew_2: 'Crew 2',
  crew_3: 'Crew 3',
  crew_4: 'Crew 4',
}

export function ProjectLobbyPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { currentProject, fetchProject, isLoading } = useProjectStore()
  const { seats, setSeats } = useSeatStore()
  const { user } = useAuthStore()

  const [joiningRole, setJoiningRole] = useState<SeatRole | null>(null)
  const [joinError, setJoinError] = useState('')

  useEffect(() => {
    if (id) {
      fetchProject(id)
    }
  }, [id, fetchProject])

  useEffect(() => {
    if (currentProject?.seats) {
      setSeats(currentProject.seats)
    }
  }, [currentProject?.seats, setSeats])

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
    <div>
      {/* Breadcrumb */}
      <div className="mb-6 flex items-center gap-2 text-sm text-text-muted">
        <Link to="/projects" className="flex items-center gap-1 hover:text-text transition-colors">
          <ChevronLeft size={16} />
          返回專案列表
        </Link>
      </div>

      {/* Project header */}
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-text">{currentProject.name}</h1>
          <PhaseIndicator phase={currentProject.current_stage} />
        </div>
        <p className="mt-1 text-sm text-text-muted">
          AI 貢獻度：{AI_LABELS[currentProject.ai_contribution]}
        </p>
      </div>

      {/* Description */}
      {currentProject.description && (
        <div className="mb-6 rounded-xl bg-surface p-5 border border-border shadow-sm">
          <h2 className="mb-2 text-sm font-semibold text-text">工作坊主題</h2>
          <p className="text-sm text-text-muted leading-relaxed">{currentProject.description}</p>
        </div>
      )}

      {/* Seat selection */}
      <div className="mb-6">
        <h2 className="mb-4 text-base font-semibold text-text">選擇席位加入</h2>

        {joinError && (
          <div className="mb-4 rounded-md bg-error-bg px-4 py-3 text-sm text-error">
            {joinError}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
          {seats.map((seat) => {
            const isAI = seat.occupant_type === 'ai'
            const isOccupied = seat.occupant_type !== null
            const isMyCurrentSeat = myCurrentSeat?.seat_role === seat.seat_role
            const isJoining = joiningRole === seat.seat_role

            return (
              <button
                key={seat.id}
                onClick={() => !isAI && !isMyCurrentSeat && handleJoin(seat.seat_role as SeatRole)}
                disabled={isAI || isJoining}
                className={cn(
                  'flex flex-col items-center gap-2 rounded-xl border p-4 text-sm transition-all',
                  isMyCurrentSeat && 'border-primary bg-primary/10 text-primary',
                  isAI && 'border-border bg-secondary/20 text-text-muted cursor-default',
                  !isOccupied && !isMyCurrentSeat && 'border-border bg-surface hover:border-primary/40 hover:bg-primary/5 cursor-pointer',
                  isOccupied && !isAI && !isMyCurrentSeat && 'border-accent/40 bg-accent/10 text-text-muted cursor-default',
                )}
              >
                {isAI ? (
                  <Bot size={20} className="text-text-muted" />
                ) : (
                  <User size={20} className={isMyCurrentSeat ? 'text-primary' : 'text-text-muted'} />
                )}
                <span className="font-medium">{SEAT_ROLE_LABELS[seat.seat_role] ?? seat.seat_role}</span>
                {isOccupied && (
                  <span className="text-xs text-text-muted truncate max-w-full">
                    {seat.display_name ?? (isAI ? 'AI' : '已佔用')}
                  </span>
                )}
                {!isOccupied && (
                  <span className="text-xs text-text-muted">空席</span>
                )}
                {isJoining && (
                  <span className="text-xs text-primary">加入中…</span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* Enter workspace */}
      {myCurrentSeat ? (
        <div className="flex justify-center">
          <Button size="lg" onClick={handleEnterWorkspace} className="min-w-48">
            進入工作區
          </Button>
        </div>
      ) : (
        <div className="mt-4 flex flex-col items-center gap-2 text-center">
          <p className="text-sm text-text-muted">也可以不佔席位，以觀察者身份進入</p>
          <Button variant="ghost" onClick={handleEnterWorkspace}>
            以觀察者身份進入
          </Button>
        </div>
      )}

      {/* Seat bar preview */}
      {seats.length > 0 && (
        <div className="mt-8 pt-6 border-t border-border">
          <p className="mb-3 text-xs font-medium text-text-muted uppercase tracking-wide">目前席位概況</p>
          <SeatBar seats={seats} currentUserId={user?.id} />
        </div>
      )}
    </div>
  )
}
