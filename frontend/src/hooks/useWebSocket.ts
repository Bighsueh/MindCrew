import { useEffect, useRef, useCallback, useState } from 'react'
import { getAccessToken } from '../services/api'
import type { WSMessage, WSClientMessage } from '../types/ws'

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'failed'

interface UseWebSocketOptions {
  onMessage?: (msg: WSMessage) => void
  onOpen?: () => void
  onClose?: () => void
  enabled?: boolean
}

const HEARTBEAT_INTERVAL = 30_000
const MAX_RETRIES = 5
const RETRY_BASE_DELAY = 1_000
// 快速退避用罄後，不永久放棄——改每 SLOW_RETRY_DELAY 慢速重試一次。連回時 onOpen → resync
// 自動補回斷線期間遺失的狀態（取代叫使用者「整頁重整」；盲測 2026-06-09 R5 學生被迫重整）。
const SLOW_RETRY_DELAY = 20_000

export function useWebSocket(url: string, options: UseWebSocketOptions = {}) {
  const { onMessage, onOpen, onClose, enabled = true } = options

  const wsRef = useRef<WebSocket | null>(null)
  const retriesRef = useRef(0)
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  // Store callbacks in refs to avoid re-triggering connect/effect on every render
  const onMessageRef = useRef(onMessage)
  const onOpenRef = useRef(onOpen)
  const onCloseRef = useRef(onClose)
  onMessageRef.current = onMessage
  onOpenRef.current = onOpen
  onCloseRef.current = onClose

  const [status, setStatus] = useState<ConnectionStatus>('disconnected')

  const clearHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current)
      heartbeatRef.current = null
    }
  }, [])

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
  }, [])

  const send = useCallback((msg: WSClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  const connect = useCallback(() => {
    if (!mountedRef.current || !enabled) return

    const token = getAccessToken()
    const wsUrl = `${url}${url.includes('?') ? '&' : '?'}token=${token ?? ''}`

    setStatus('connecting')
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      retriesRef.current = 0
      setStatus('connected')
      onOpenRef.current?.()

      clearHeartbeat()
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping', payload: {} }))
        }
      }, HEARTBEAT_INTERVAL)
    }

    ws.onmessage = (event: MessageEvent) => {
      if (!mountedRef.current) return
      try {
        const msg = JSON.parse(event.data as string) as WSMessage
        // Respond to server pings
        if (msg.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong', payload: {} }))
          return
        }
        onMessageRef.current?.(msg)
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      clearHeartbeat()
      setStatus('disconnected')
      onCloseRef.current?.()

      if (retriesRef.current < MAX_RETRIES) {
        const delay = RETRY_BASE_DELAY * Math.pow(2, retriesRef.current)
        retriesRef.current += 1
        reconnectTimerRef.current = setTimeout(connect, delay)
      } else {
        // 標 failed 顯示橫幅，但**持續慢速重試**（不永久放棄）；重置退避計數，
        // 每 SLOW_RETRY_DELAY 再連一次，連回即 onOpen → resync 補回狀態。
        setStatus('failed')
        retriesRef.current = 0
        reconnectTimerRef.current = setTimeout(connect, SLOW_RETRY_DELAY)
      }
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [url, enabled, clearHeartbeat])

  useEffect(() => {
    mountedRef.current = true
    if (enabled) connect()

    return () => {
      mountedRef.current = false
      clearReconnectTimer()
      clearHeartbeat()
      wsRef.current?.close()
    }
  }, [connect, enabled, clearReconnectTimer, clearHeartbeat])

  return { status, send }
}
