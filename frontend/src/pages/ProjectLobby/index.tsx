import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useProjectStore } from '../../stores/projectStore'
import { useSeatStore } from '../../stores/seatStore'
import { useAuthStore } from '../../stores/authStore'
import { joinProject } from '../../services/projectService'
import { SeatCard } from '../../components/seats/SeatCard'
import { Button } from '../../components/common/Button'
import { Loading } from '../../components/common/Loading'
import type { SeatRole } from '../../types/models'

const STAGE_LABELS = {
  discover: '🔍 發現',
  define: '📌 定義',
  develop: '💡 發展',
  deliver: '🚀 交付',
  completed: '✅ 完成',
}

const AI_LABELS = {
  low: '低',
  medium: '中',
  high: '高',
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

  // Find if current user already holds a seat
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
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center gap-4">
          <Link to="/projects" className="text-sm text-gray-500 hover:text-gray-700">
            ← 返回
          </Link>
          <div className="flex-1">
            <h1 className="text-lg font-bold text-gray-900">{currentProject.name}</h1>
            <div className="flex items-center gap-3 text-sm text-gray-500">
              <span>{STAGE_LABELS[currentProject.current_stage]}</span>
              <span>AI 貢獻度：{AI_LABELS[currentProject.ai_contribution]}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto max-w-4xl px-6 py-8">
        {/* Description */}
        {currentProject.description && (
          <div className="mb-6 rounded-xl bg-white p-5 border border-gray-200 shadow-sm">
            <h2 className="mb-2 text-sm font-semibold text-gray-700">工作坊主題</h2>
            <p className="text-sm text-gray-600 leading-relaxed">{currentProject.description}</p>
          </div>
        )}

        {/* Seat selection */}
        <div className="mb-6">
          <h2 className="mb-4 text-base font-semibold text-gray-800">選擇席位加入</h2>

          {joinError && (
            <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
              {joinError}
            </div>
          )}

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-5">
            {seats.map((seat) => (
              <SeatCard
                key={seat.id}
                seat={seat}
                currentUserSeatRole={myCurrentSeat?.seat_role}
                onJoin={handleJoin}
                isJoining={joiningRole === seat.seat_role}
              />
            ))}
          </div>
        </div>

        {/* Enter workspace button if already joined */}
        {myCurrentSeat && (
          <div className="flex justify-center">
            <Button size="lg" onClick={handleEnterWorkspace} className="min-w-48">
              進入工作區 →
            </Button>
          </div>
        )}

        {/* Observer mode — enter without seat */}
        {!myCurrentSeat && (
          <div className="mt-4 flex flex-col items-center gap-2 text-center">
            <p className="text-sm text-gray-500">也可以不佔席位，以觀察者身份進入</p>
            <Button variant="ghost" onClick={handleEnterWorkspace}>
              以觀察者身份進入
            </Button>
          </div>
        )}
      </main>
    </div>
  )
}
