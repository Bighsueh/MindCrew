import { Wifi, WifiOff } from 'lucide-react'

interface ConnectionBannerProps {
  status: 'connecting' | 'disconnected' | 'failed'
}

export function ConnectionBanner({ status }: ConnectionBannerProps) {
  const isFailed = status === 'failed'

  return (
    <div
      className={
        isFailed
          ? 'flex items-center justify-center gap-2 bg-error px-4 py-2 text-sm font-medium text-text-inverse'
          : 'flex items-center justify-center gap-2 bg-warning px-4 py-2 text-sm font-medium text-text-inverse'
      }
      role="alert"
    >
      {isFailed ? (
        <>
          <WifiOff size={16} />
          連線不穩，仍在自動嘗試重連…（資料每幾秒會自動同步，不需手動重整）
        </>
      ) : (
        <>
          <Wifi size={16} className="animate-pulse" />
          連線中斷，嘗試重新連線…
        </>
      )}
    </div>
  )
}
