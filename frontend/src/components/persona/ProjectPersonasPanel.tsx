import { useMemo, useState } from 'react'
import { Modal } from '../common/Modal'
import { Button } from '../common/Button'
import { PersonaCard } from './PersonaCard'
import { PersonaEditDialog } from './PersonaEditDialog'
import { emptyPersona } from './personaUtils'
import { updateSeatPersona } from '../../services/projectService'
import type { CrewSeatRole, Persona, Seat } from '../../types/models'

interface ProjectPersonasPanelProps {
  isOpen: boolean
  projectId: string
  seats: Seat[]
  onClose: () => void
  onUpdated: (updated: Seat) => void
}

const CREW_ROLES: CrewSeatRole[] = ['crew_1', 'crew_2', 'crew_3', 'crew_4']

export function ProjectPersonasPanel({
  isOpen,
  projectId,
  seats,
  onClose,
  onUpdated,
}: ProjectPersonasPanelProps) {
  const [editingSeat, setEditingSeat] = useState<CrewSeatRole | null>(null)
  const [error, setError] = useState('')

  const seatsByRole = useMemo(() => {
    const map = new Map<CrewSeatRole, Seat>()
    for (const seat of seats) {
      if (CREW_ROLES.includes(seat.seat_role as CrewSeatRole)) {
        map.set(seat.seat_role as CrewSeatRole, seat)
      }
    }
    return map
  }, [seats])

  const personaForRole = (role: CrewSeatRole): Persona => {
    const seat = seatsByRole.get(role)
    if (seat?.persona) return seat.persona
    const draft = emptyPersona()
    return {
      ...draft,
      name: seat?.display_name ?? '',
    }
  }

  const handleSave = async (role: CrewSeatRole, persona: Persona) => {
    setError('')
    try {
      const updated = await updateSeatPersona(projectId, role, persona)
      onUpdated(updated)
      setEditingSeat(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : '儲存失敗，請稍後再試。'
      setError(message)
      throw err
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="AI 隊友人設" maxWidth="xl">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-text-muted leading-relaxed">
          這裡是目前專案的 AI 隊友。點任一張卡片可以調整他的身分、專長、個性與認知透鏡。
          人設修改後，該位 AI 會立即套用新的人設重新啟動。
        </p>
        {error && (
          <div className="rounded-md bg-error-bg px-3 py-2 text-sm text-error">
            {error}
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {CREW_ROLES.map((role, idx) => {
            const seat = seatsByRole.get(role)
            const persona = personaForRole(role)
            const isHuman = seat?.occupant_type === 'human'
            return (
              <div key={role} className="flex flex-col gap-2">
                <PersonaCard
                  persona={persona}
                  index={idx}
                  onEdit={isHuman ? undefined : () => setEditingSeat(role)}
                />
                {isHuman && (
                  <p className="text-[11px] text-text-muted">
                    此座位目前由人類成員佔據，無法編輯人設。
                  </p>
                )}
              </div>
            )
          })}
        </div>
        <div className="flex justify-end pt-2">
          <Button variant="secondary" onClick={onClose}>
            關閉
          </Button>
        </div>
      </div>

      {editingSeat && (
        <PersonaEditDialog
          isOpen
          initial={personaForRole(editingSeat)}
          title={`編輯 ${editingSeat}`}
          onClose={() => setEditingSeat(null)}
          onSave={(persona) => handleSave(editingSeat, persona)}
        />
      )}
    </Modal>
  )
}
