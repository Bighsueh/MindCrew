import { useState } from 'react'
import { Modal } from '../common/Modal'
import { Button } from '../common/Button'
import { AlertTriangle } from 'lucide-react'

interface DeleteProjectDialogProps {
  isOpen: boolean
  projectName: string
  onClose: () => void
  onConfirm: () => Promise<void>
}

export function DeleteProjectDialog({
  isOpen,
  projectName,
  onClose,
  onConfirm,
}: DeleteProjectDialogProps) {
  const [confirmText, setConfirmText] = useState('')
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState('')

  const canConfirm = confirmText === projectName

  const handleConfirm = async () => {
    if (!canConfirm) return
    setIsDeleting(true)
    setError('')
    try {
      await onConfirm()
      setConfirmText('')
      onClose()
    } catch {
      setError('刪除失敗，請稍後再試。')
    } finally {
      setIsDeleting(false)
    }
  }

  const handleClose = () => {
    if (isDeleting) return
    setConfirmText('')
    setError('')
    onClose()
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="刪除學習活動">
      <div className="flex flex-col gap-4">
        <div className="flex items-start gap-3 rounded-lg bg-error-bg p-4">
          <AlertTriangle size={20} className="mt-0.5 shrink-0 text-error" />
          <div className="text-sm text-text">
            <p className="font-medium">此操作無法復原。</p>
            <p className="mt-1 text-text-muted">
              此學習活動中的所有對話紀錄、白板內容、Agent 決策日誌都將被永久刪除。
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm text-text-muted">
            請輸入 <span className="font-semibold text-text">{projectName}</span> 以確認刪除
          </label>
          <input
            type="text"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder={projectName}
            className="rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-text
                       placeholder:text-text-muted/40
                       focus:border-error focus:outline-none focus:ring-2 focus:ring-error/20"
            autoFocus
          />
        </div>

        {error && (
          <div className="rounded-md bg-error-bg px-4 py-3 text-sm text-error">
            {error}
          </div>
        )}

        <div className="flex gap-3">
          <Button variant="secondary" className="flex-1" onClick={handleClose} disabled={isDeleting}>
            取消
          </Button>
          <Button
            variant="danger"
            className="flex-1"
            disabled={!canConfirm}
            isLoading={isDeleting}
            onClick={handleConfirm}
          >
            永久刪除
          </Button>
        </div>
      </div>
    </Modal>
  )
}
