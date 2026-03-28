import { Eye, ArrowRight } from 'lucide-react'
import { Button } from '../../components/common/Button'

interface ObserverCardProps {
  onEnter: () => void
  hasCurrentSeat: boolean
}

export function ObserverCard({ onEnter, hasCurrentSeat }: ObserverCardProps) {
  return (
    <div className="flex flex-col rounded-2xl bg-surface p-6 shadow-md">
      <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-info/10 text-info">
        <Eye size={20} />
      </div>

      {hasCurrentSeat ? (
        <>
          <h3 className="mb-1 text-base font-semibold text-text">
            進入工作區
          </h3>
          <p className="mb-auto text-xs leading-relaxed text-text-muted">
            你已選擇席位，點擊下方按鈕開始參與討論
          </p>
          <Button onClick={onEnter} className="mt-5 w-full">
            <span className="flex items-center justify-center gap-1.5">
              <ArrowRight size={16} />
              進入工作區
            </span>
          </Button>
        </>
      ) : (
        <>
          <h3 className="mb-1 text-base font-semibold text-text">
            觀察者模式
          </h3>
          <p className="mb-auto text-xs leading-relaxed text-text-muted">
            不佔席位，以觀察者身份查看即時討論與白板。適合教師巡視或旁聽使用。
          </p>
          <Button variant="secondary" onClick={onEnter} className="mt-5 w-full">
            <span className="flex items-center justify-center gap-1.5">
              <Eye size={14} />
              以觀察者身份進入
            </span>
          </Button>
        </>
      )}
    </div>
  )
}
