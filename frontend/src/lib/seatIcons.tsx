import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import {
  faUserSecret,
  faUserTie,
  faUserNinja,
  faUserAstronaut,
  faCrown,
  faUser,
} from '@fortawesome/free-solid-svg-icons'
import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'

const CREW_AI_ICONS: Record<string, IconDefinition> = {
  crew_1: faUserSecret,
  crew_2: faUserTie,
  crew_3: faUserNinja,
  crew_4: faUserAstronaut,
}

export function getSeatIcon(opts: {
  seatRole: string
  isAI: boolean
  isSupervisor: boolean
}): IconDefinition {
  const { seatRole, isAI, isSupervisor } = opts
  if (isSupervisor) return faCrown
  if (isAI) return CREW_AI_ICONS[seatRole] ?? faUserAstronaut
  return faUser
}

interface SeatIconProps {
  seatRole: string
  isAI: boolean
  isSupervisor: boolean
  size?: number
  className?: string
}

export function SeatIcon({
  seatRole,
  isAI,
  isSupervisor,
  size,
  className,
}: SeatIconProps) {
  const icon = getSeatIcon({ seatRole, isAI, isSupervisor })
  return (
    <FontAwesomeIcon
      icon={icon}
      className={className}
      style={size ? { width: size, height: size } : undefined}
    />
  )
}
