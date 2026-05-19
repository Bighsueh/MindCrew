import { useProjectStore } from '../stores/projectStore'
import { getColorScheme } from '../colors/sticky'

/**
 * Phase 22：依 author 識別席位色。
 *
 * - human 訊息：用 `sender_id` 對到 seat.user_id
 * - ai 訊息：用 `sender_id` 對到 seat.agent_id
 *
 * 找不到 → 回 fallback。
 */
export function useAuthorColor(
  senderId: string | null | undefined,
  senderType: 'human' | 'ai' | 'system',
) {
  const seats = useProjectStore((s) => s.currentProject?.seats ?? [])

  if (!senderId || senderType === 'system') {
    return { token: null, scheme: getColorScheme(null) }
  }

  const seat = seats.find((s) => {
    if (senderType === 'human') return s.user_id === senderId
    return s.agent_id === senderId
  })

  return {
    token: seat?.sticky_color ?? null,
    scheme: getColorScheme(seat?.sticky_color),
  }
}
