import { useState } from 'react'
import { MessageSquare } from 'lucide-react'
import { cn } from '../../lib/utils'
import { Button } from '../common/Button'
import { Modal } from '../common/Modal'
import { useProjectStore } from '../../stores/projectStore'
import type { TurnPolicy } from '../../types/models'

const POLICY_LABELS: Record<TurnPolicy, string> = {
  cued: '點名（Cued）',
  round_robin: '輪流（Round-Robin）',
  open_floor: '搶答（Open-Floor）',
}

const POLICY_HINTS: Record<TurnPolicy, string> = {
  cued: '由 Supervisor 主持，點名指定的成員回應',
  round_robin: '依固定順序輪流發言；輪完一圈自動重啟',
  open_floor: '所有人可以主動發言；學生按「我要發言」可優先',
}

const POLICY_OPTIONS: TurnPolicy[] = ['cued', 'round_robin', 'open_floor']

interface TurnPolicySwitcherProps {
  projectId: string
  projectName?: string
  currentPolicy: TurnPolicy
  /** 切換成功後的 callback (例如父層 onRefresh)。 */
  onChange?: (policy: TurnPolicy) => void
  /** 緊湊版（卡片內）用 sm 尺寸下拉；workspace 頂端 bar 用 md。 */
  compact?: boolean
  /** 額外 className 套到外層容器。 */
  className?: string
}

/**
 * Phase 28 /  — 教師專用模式選擇器。
 *
 * 下拉選 + 確認 modal + toast。實際 PATCH 由 projectStore.setTurnPolicy 執行，
 * 後端會 publish ``turn_policy_changed`` 廣播給所有 WS 訂閱者。
 */
export function TurnPolicySwitcher({
  projectId,
  projectName,
  currentPolicy,
  onChange,
  compact = false,
  className,
}: TurnPolicySwitcherProps) {
  const setTurnPolicy = useProjectStore((s) => s.setTurnPolicy)
  const [pendingPolicy, setPendingPolicy] = useState<TurnPolicy | null>(null)
  const [isSwitching, setIsSwitching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSelect = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const next = event.target.value as TurnPolicy
    if (next === currentPolicy) return
    setPendingPolicy(next)
    setError(null)
  }

  const handleConfirm = async () => {
    if (!pendingPolicy) return
    setIsSwitching(true)
    setError(null)
    try {
      await setTurnPolicy(projectId, pendingPolicy)
      onChange?.(pendingPolicy)
      setPendingPolicy(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : '切換輪流規則失敗'
      setError(message)
    } finally {
      setIsSwitching(false)
    }
  }

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <MessageSquare
        size={compact ? 12 : 14}
        className="text-text-muted shrink-0"
      />
      <label
        className={cn(
          'text-text-muted whitespace-nowrap',
          compact ? 'text-xs' : 'text-sm',
        )}
        htmlFor={`turn-policy-${projectId}`}
      >
        對話模式
      </label>
      <select
        id={`turn-policy-${projectId}`}
        value={currentPolicy}
        onChange={handleSelect}
        disabled={isSwitching}
        className={cn(
          'rounded-md border border-border bg-bg text-text',
          'focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          compact ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm',
        )}
        aria-label="切換對話模式"
        data-testid="turn-policy-select"
      >
        {POLICY_OPTIONS.map((policy) => (
          <option key={policy} value={policy}>
            {POLICY_LABELS[policy]}
          </option>
        ))}
      </select>

      <Modal
        isOpen={pendingPolicy !== null}
        onClose={() => {
          if (!isSwitching) setPendingPolicy(null)
        }}
        title="切換對話模式"
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm text-text-muted">
            確定要把
            {projectName ? (
              <>
                {' '}<strong className="text-text">{projectName}</strong>{' '}
              </>
            ) : (
              '此活動'
            )}
            的對話模式改為
            <strong className="text-primary">
              {' '}{pendingPolicy ? POLICY_LABELS[pendingPolicy] : ''}{' '}
            </strong>
            嗎？
          </p>
          <div className="rounded-lg bg-bg p-3 text-sm">
            <div className="text-text-muted text-xs mb-1">模式說明</div>
            <div className="text-text">
              {pendingPolicy ? POLICY_HINTS[pendingPolicy] : ''}
            </div>
          </div>
          <p className="text-xs text-text-muted">
            此變更會立即生效（agent 下一個決策週期 ≤ 1 秒）。
          </p>
          {error && (
            <div className="rounded-md bg-error/10 px-3 py-2 text-xs text-error">
              {error}
            </div>
          )}
          <div className="flex gap-3">
            <Button
              variant="secondary"
              className="flex-1"
              onClick={() => setPendingPolicy(null)}
              disabled={isSwitching}
            >
              取消
            </Button>
            <Button
              className="flex-1"
              isLoading={isSwitching}
              onClick={handleConfirm}
            >
              確認切換
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
