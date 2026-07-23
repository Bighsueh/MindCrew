import { NavLink } from 'react-router-dom'
import { cn } from '../../lib/utils'

const TABS = [
  { to: '/admin/providers', label: 'Providers' },
  { to: '/admin/llm-health', label: 'LLM Health' },
  { to: '/admin/logs', label: 'Request Logs' },
  { to: '/admin/stats', label: 'Stats' },
] as const

export function AdminNav() {
  return (
    <nav className="border-b border-border" data-testid="admin-nav">
      <div className="flex items-center gap-2 px-1">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            className={({ isActive }) =>
              cn(
                'px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors',
                isActive
                  ? 'border-primary text-primary'
                  : 'border-transparent text-text-muted hover:text-text',
              )
            }
          >
            {t.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
