import { useNavigate } from 'react-router-dom'
import { Modal } from '../common/Modal'
import { Button } from '../common/Button'
import { PartyPopper } from 'lucide-react'

interface ProjectCreatedDialogProps {
  isOpen: boolean
  projectId: string
  projectName: string
  /** 「留在列表」/ 關閉。 */
  onClose: () => void
}

/**
 * 建立設計專案成功後跳出，詢問是否立即進入剛建立的活動。
 * 「進入專案」導向該活動的 lobby；「留在列表」僅關閉本對話框。
 */
export function ProjectCreatedDialog({
  isOpen,
  projectId,
  projectName,
  onClose,
}: ProjectCreatedDialogProps) {
  const navigate = useNavigate()

  const handleEnter = () => {
    onClose()
    navigate(`/projects/${projectId}/lobby`)
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="設計專案建立成功 🎉">
      <div className="flex flex-col gap-5">
        <div className="flex items-start gap-3 rounded-lg bg-success/10 p-4">
          <PartyPopper size={20} className="mt-0.5 shrink-0 text-success" />
          <p className="text-sm text-text">
            「
            <span className="font-semibold text-text">{projectName}</span>
            」已經建立完成，要現在直接進入嗎？
          </p>
        </div>

        <div className="flex gap-3">
          <Button variant="secondary" className="flex-1" onClick={onClose}>
            留在列表
          </Button>
          <Button className="flex-1" onClick={handleEnter}>
            進入專案
          </Button>
        </div>
      </div>
    </Modal>
  )
}
