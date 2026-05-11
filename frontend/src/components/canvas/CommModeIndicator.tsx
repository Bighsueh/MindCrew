/**
 * Comm mode indicator — Spec 13 §3.
 *
 * 左上角 floating badge：顯示當前互動模式（sub-phase + comm_mode）。
 * silent_write / silent_rearrange 時把 chat 框灰化。
 */

interface CommModeIndicatorProps {
  subPhase: string | null;
  commMode: 'silent_write' | 'reveal_round' | 'silent_rearrange' | 'discussion';
  subPhaseName?: string;
  nextRevealSeat?: string | null;
}

const MODE_LABELS: Record<string, { label: string; icon: string; color: string }> = {
  silent_write: { label: '沉默寫', icon: '🚫', color: '#dc2626' },
  reveal_round: { label: '揭示輪', icon: '🔁', color: '#ea580c' },
  silent_rearrange: { label: '沉默重排', icon: '🤐', color: '#7c3aed' },
  discussion: { label: '自由討論', icon: '💬', color: '#16a34a' },
};

export function CommModeIndicator({
  subPhase,
  commMode,
  subPhaseName,
  nextRevealSeat,
}: CommModeIndicatorProps) {
  if (!subPhase) return null;
  const m = MODE_LABELS[commMode] ?? MODE_LABELS.discussion;

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: 'absolute',
        top: 8,
        left: 8,
        background: 'rgba(255,255,255,0.95)',
        border: `2px solid ${m.color}`,
        borderRadius: '8px',
        padding: '6px 12px',
        fontSize: '13px',
        fontWeight: 600,
        zIndex: 50,
        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
        minHeight: '44px',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
      }}
    >
      <span>{m.icon}</span>
      <span style={{ color: m.color }}>{m.label}</span>
      <span style={{ color: '#6b7280', fontWeight: 500 }}>
        ｜ {subPhase}
        {subPhaseName ? ` ${subPhaseName}` : ''}
      </span>
      {commMode === 'reveal_round' && nextRevealSeat && (
        <span style={{ color: '#0369a1' }}>｜ 輪到 {nextRevealSeat}</span>
      )}
    </div>
  );
}

export function isChatDisabled(
  commMode: 'silent_write' | 'reveal_round' | 'silent_rearrange' | 'discussion',
): boolean {
  return commMode === 'silent_write' || commMode === 'silent_rearrange';
}
