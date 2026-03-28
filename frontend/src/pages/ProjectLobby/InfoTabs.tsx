import { useState } from 'react'
import { Radio, BarChart3, StickyNote, Sparkles } from 'lucide-react'
import { cn } from '../../lib/utils'
import { LiveActivityFeed } from './LiveActivityFeed'
import { ProjectDashboardStats } from './ProjectDashboardStats'
import { CanvasThumbnail } from './CanvasThumbnail'
import { QuickSummaryPanel } from './QuickSummaryPanel'
import type { Message, StageInfo, StageHistoryEntry, AIContribution, CanvasStateResponse } from '../../types/models'

interface TypingUser {
  name: string
  isTyping: boolean
}

interface InfoTabsProps {
  messages: Message[]
  typingUsers: Map<string, TypingUser>
  wsStatus: 'connecting' | 'connected' | 'disconnected' | 'failed'
  stageInfo: StageInfo | null
  stageHistory: StageHistoryEntry[]
  messageCount: number
  noteCount: number
  aiContribution: AIContribution
  canvasState: CanvasStateResponse | null
  projectId: string
}

const TABS = [
  { key: 'activity', label: '即時動態', icon: Radio },
  { key: 'stats', label: '專案概況', icon: BarChart3 },
  { key: 'canvas', label: '白板預覽', icon: StickyNote },
  { key: 'summary', label: '快速摘要', icon: Sparkles },
] as const

type TabKey = (typeof TABS)[number]['key']

export function InfoTabs({
  messages,
  typingUsers,
  wsStatus,
  stageInfo,
  stageHistory,
  messageCount,
  noteCount,
  aiContribution,
  canvasState,
  projectId,
}: InfoTabsProps) {
  const [activeTab, setActiveTab] = useState<TabKey>('activity')

  return (
    <div className="rounded-xl border border-border bg-surface shadow-sm">
      {/* Tab bar */}
      <div className="flex border-b border-border px-2">
        {TABS.map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.key
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'flex items-center gap-1.5 px-4 py-3 text-sm transition-colors',
                isActive
                  ? 'border-b-2 border-primary font-medium text-primary'
                  : 'text-text-muted hover:text-text',
              )}
            >
              <Icon size={14} />
              <span className="hidden sm:inline">{tab.label}</span>
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      <div className="p-5">
        {activeTab === 'activity' && (
          <LiveActivityFeed
            messages={messages}
            typingUsers={typingUsers}
            wsStatus={wsStatus}
            embedded
          />
        )}
        {activeTab === 'stats' && (
          <ProjectDashboardStats
            stageInfo={stageInfo}
            stageHistory={stageHistory}
            messageCount={messageCount}
            noteCount={noteCount}
            aiContribution={aiContribution}
            embedded
          />
        )}
        {activeTab === 'canvas' && (
          <CanvasThumbnail canvasState={canvasState} embedded />
        )}
        {activeTab === 'summary' && (
          <QuickSummaryPanel projectId={projectId} embedded />
        )}
      </div>
    </div>
  )
}
