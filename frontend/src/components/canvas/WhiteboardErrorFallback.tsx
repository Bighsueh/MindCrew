/**
 * WhiteboardErrorFallback — 取代 tldraw 預設的全編輯器錯誤畫面。
 *
 * 為什麼需要：tldraw 內建的 ErrorBoundary 一旦攔到任何渲染錯誤（即使只是某一瞬間的
 * 暫態 throw），就會把「整面白板」鎖在錯誤畫面、且只能整頁 refresh 才能復原
 * （預設畫面還會叫使用者去開 GitHub issue / Discord，對終端使用者沒意義）。
 *
 * 這個元件做兩件事：
 *  1. 把真正的錯誤 `console.error` 出來 —— 暫態崩潰下次再發生時就能在 console 抓到堆疊。
 *  2. 提供「重新載入白板」按鈕，由父層用 remount（換 key）原地復原，不丟失頁面狀態與資料。
 */
import { useEffect } from 'react'

interface WhiteboardErrorFallbackProps {
  error: unknown
  onReload: () => void
}

export function WhiteboardErrorFallback({ error, onReload }: WhiteboardErrorFallbackProps) {
  useEffect(() => {
    // 真錯誤一律印出來，方便診斷暫態崩潰（取代 tldraw 預設「開 issue」畫面的功能）。
    console.error('[Whiteboard] tldraw render error caught by ErrorFallback:', error)
  }, [error])

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-[#faf0e6]/95">
      <div className="mx-4 flex max-w-sm flex-col items-center gap-3 rounded-2xl border border-[#e6d7c8] bg-white/90 px-6 py-7 text-center shadow-lg">
        <div className="text-3xl" aria-hidden="true">
          🩹
        </div>
        <h2 className="text-base font-semibold text-[#5A4D41]">白板暫時出了點狀況</h2>
        <p className="text-sm leading-relaxed text-[#8a7a6a]">
          已自動隔離問題，你的便利貼與討論都還在。
          <br />
          重新載入白板就能繼續，不會遺失資料。
        </p>
        <button
          type="button"
          onClick={onReload}
          className="mt-1 rounded-full bg-[#bd6c48] px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-[#a85c3b]"
        >
          重新載入白板
        </button>
      </div>
    </div>
  )
}
