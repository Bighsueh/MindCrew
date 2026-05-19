import { LogIn, ArrowRight, Users } from 'lucide-react'
import { Button } from '../../components/common/Button'

interface JoinSeatCardProps {
  onJoin: () => void
  onEnter: () => void
  hasCurrentSeat: boolean
  canJoin: boolean
  isLocked?: boolean
  projectFull: boolean
}

export function JoinSeatCard({
  onJoin,
  onEnter,
  hasCurrentSeat,
  canJoin,
  isLocked = false,
  projectFull,
}: JoinSeatCardProps) {
  if (hasCurrentSeat) {
    return (
      <div className="flex flex-col rounded-2xl bg-surface p-6 shadow-md">
        <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Users size={20} />
        </div>
        <h3 className="mb-1 text-base font-semibold text-text">進入工作區</h3>
        <p className="mb-auto text-xs leading-relaxed text-text-muted">
          你已加入這個學習活動，點擊下方按鈕開始參與討論。
        </p>
        <Button onClick={onEnter} className="mt-5 w-full" disabled={isLocked}>
          <span className="flex items-center justify-center gap-1.5">
            <ArrowRight size={16} />
            進入工作區
          </span>
        </Button>
      </div>
    )
  }

  const disabledReason = projectFull
    ? '此學習活動已有人類參與者'
    : !canJoin
      ? '目前沒有可用席位'
      : undefined

  return (
    <div className="flex flex-col rounded-2xl bg-surface p-6 shadow-md">
      <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <LogIn size={20} />
      </div>
      <h3 className="mb-1 text-base font-semibold text-text">加入這個學習活動</h3>
      <p className="mb-auto text-xs leading-relaxed text-text-muted">
        點擊下方按鈕，系統會自動為你安排席位並啟動 AI 組員。
      </p>
      <Button
        onClick={onJoin}
        size="lg"
        className="mt-5 w-full"
        disabled={isLocked || !!disabledReason}
        title={disabledReason}
      >
        <span className="flex items-center justify-center gap-1.5">
          <LogIn size={18} />
          {disabledReason ?? '加入討論'}
        </span>
      </Button>
    </div>
  )
}
