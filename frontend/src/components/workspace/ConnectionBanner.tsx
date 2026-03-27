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
          無法連線，請檢查網路後重新整理頁面。
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
