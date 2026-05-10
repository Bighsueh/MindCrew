/**
 * HMW tab bar — Spec 13 §2.4.
 *
 * 當 active HMW 數量 >= 2 時顯示頂部 tab bar。
 */

import { useHmwTabsStore } from '@/stores/hmwTabsStore';

export function HmwTabBar() {
  const tabs = useHmwTabsStore((s) => s.tabs);
  const activeHmwId = useHmwTabsStore((s) => s.activeHmwId);
  const setActive = useHmwTabsStore((s) => s.setActive);

  if (tabs.length < 2) return null;

  return (
    <div
      role="tablist"
      style={{
        position: 'absolute',
        top: 8,
        left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex',
        gap: '4px',
        zIndex: 50,
        background: 'rgba(255,255,255,0.92)',
        padding: '4px',
        borderRadius: '8px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
      }}
    >
      {tabs.map((t) => {
        const isActive = t.hmwId === activeHmwId;
        return (
          <button
            key={t.hmwId}
            role="tab"
            aria-selected={isActive}
            data-active={isActive}
            className="hmw-tab"
            onClick={() => setActive(t.hmwId)}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              fontSize: '13px',
              fontWeight: 600,
              border: 'none',
              cursor: 'pointer',
              background: isActive ? '#3b82f6' : '#dbeafe',
              color: isActive ? '#fff' : '#1e3a8a',
              minHeight: '44px', // 拇指可點
            }}
          >
            {truncate(t.label, 28)}
          </button>
        );
      })}
    </div>
  );
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + '…';
}
