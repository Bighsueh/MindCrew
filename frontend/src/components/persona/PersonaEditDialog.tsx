import { Modal } from '../common/Modal'
import { PersonaForm } from './PersonaForm'
import type { Persona } from '../../types/models'

interface PersonaEditDialogProps {
  isOpen: boolean
  initial: Persona
  title?: string
  onClose: () => void
  onSave: (persona: Persona) => void | Promise<void>
}

/**
 * PersonaEditDialog — Modal 版人設編輯（ProjectPersonasPanel 用）。
 * 欄位本體共用 {@link PersonaForm}，與座位卡內嵌編輯保持一致。
 */
export function PersonaEditDialog({
  isOpen,
  initial,
  title = '編輯人設',
  onClose,
  onSave,
}: PersonaEditDialogProps) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} maxWidth="lg">
      <PersonaForm initial={initial} onSave={onSave} onCancel={onClose} />
    </Modal>
  )
}
