/**
 * InitTimerDialog — 老師為「建立時尚未自動初始化 timer」的舊專案啟用倒數計時。
 *
 * 流程：選 preset (2hr/4hr/custom) → POST /projects/{id}/timer/init →
 *       後端 initialize_project + start_phase('1.1a') → useProjectRealtime
 *       5s polling 會自動把 snapshot.available 切成 true；同時暫時把
 *       store 標 available=true 讓畫面馬上反應。
 */

import { useState } from 'react'
import { Modal } from '../common/Modal'
import { Button } from '../common/Button'
import {
  TimerConfigForm,
  buildTimerConfig,
  DEFAULT_CUSTOM_BUDGETS,
  useTimerValidity,
  type TimerMode,
} from './TimerConfigForm'
import { initProjectTimer } from '../../services/projectService'

interface InitTimerDialogProps {
  isOpen: boolean
  projectId: string
  onClose: () => void
  onInitialized: () => void
}

export function InitTimerDialog({
  isOpen,
  projectId,
  onClose,
  onInitialized,
}: InitTimerDialogProps) {
  const [mode, setMode] = useState<TimerMode>('preset_2hr')
  const [customMacroBudgets, setCustomMacroBudgets] = useState({
    ...DEFAULT_CUSTOM_BUDGETS,
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const isValid = useTimerValidity(mode, customMacroBudgets)

  const handleSubmit = async () => {
    if (!isValid) {
      setError('時間配置總計需 ≥ 30 分鐘。')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const config = buildTimerConfig(mode, customMacroBudgets)
      await initProjectTimer(projectId, config)
      onInitialized()
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (err instanceof Error ? err.message : '啟用失敗')
      setError(detail)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="啟用倒數計時器" maxWidth="xl">
      <div className="flex flex-col gap-5">
        <p className="text-sm text-text-muted">
          這個專案建立時尚未設定計時器。選一個預設或自訂時間後，所有人就能在頁面下方看到倒數。
          啟用後會從 <span className="font-semibold text-text">sub_phase 1.1a</span> 開始計時。
        </p>

        <TimerConfigForm
          mode={mode}
          customMacroBudgets={customMacroBudgets}
          onModeChange={setMode}
          onCustomChange={setCustomMacroBudgets}
        />

        {error && (
          <div className="rounded-md bg-error-bg px-4 py-3 text-sm text-error">{error}</div>
        )}

        <div className="flex gap-3">
          <Button variant="secondary" className="flex-1" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button
            className="flex-1"
            onClick={handleSubmit}
            isLoading={submitting}
            disabled={!isValid || submitting}
          >
            啟用
          </Button>
        </div>
      </div>
    </Modal>
  )
}
