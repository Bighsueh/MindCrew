/**
 * Park sidebar — Spec 13 §6.2.
 *
 * 右側固定 sidebar，跨 phase 共用。RWD：桌機 240 / 平板直 180 / 平板橫 220。
 */

import { useEffect, useState } from 'react';

interface ParkSidebarProps {
  /** Notes currently inside park bounds. */
  notes: Array<{ id: string; text: string; color: string; authorName?: string }>;
  /** Pull a note into park (called by drop handler). */
  onDropIntoPark?: (noteId: string) => void;
  /** Pull a note out of park. */
  onDragOutOfPark?: (noteId: string) => void;
}

export function ParkSidebar({ notes, onDropIntoPark }: ParkSidebarProps) {
  const [width, setWidth] = useState(240);

  useEffect(() => {
    function updateWidth() {
      const w = window.innerWidth;
      if (w >= 1024) setWidth(240);
      else if (w >= 768 && window.innerHeight > window.innerWidth) setWidth(180);
      else setWidth(220);
    }
    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

  return (
    <aside
      className="park-sidebar"
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        width: `${width}px`,
        height: '100%',
        background: 'rgba(243, 244, 246, 0.92)',
        borderLeft: '2px dashed #9ca3af',
        padding: '12px',
        overflowY: 'auto',
        zIndex: 100,
      }}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        const noteId = e.dataTransfer?.getData('text/note-id');
        if (noteId && onDropIntoPark) onDropIntoPark(noteId);
      }}
      role="region"
      aria-label="Park 孤兒區"
    >
      <div
        style={{
          background: '#fce7f3',
          color: '#9d174d',
          padding: '8px 12px',
          borderRadius: '4px',
          fontSize: '14px',
          fontWeight: 600,
          marginBottom: '12px',
        }}
      >
        🅿️ Park（孤兒區）
      </div>

      {notes.length === 0 ? (
        <p style={{ color: '#6b7280', fontSize: '13px', textAlign: 'center' }}>
          拖入無法歸類的便條
        </p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {notes.map((n) => (
            <li
              key={n.id}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData('text/note-id', n.id);
              }}
              style={{
                background: colorFor(n.color),
                padding: '8px',
                margin: '4px 0',
                borderRadius: '4px',
                fontSize: '13px',
                lineHeight: 1.3,
                minHeight: '64px',
                cursor: 'grab',
                touchAction: 'none',
              }}
            >
              {n.text}
              {n.authorName && (
                <div style={{ fontSize: '11px', color: '#374151', marginTop: '4px' }}>
                  — {n.authorName}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

function colorFor(c: string): string {
  switch (c) {
    case 'yellow':
      return '#fef9c3';
    case 'pink':
      return '#fce7f3';
    case 'blue':
      return '#dbeafe';
    case 'green':
      return '#dcfce7';
    default:
      return '#fef9c3';
  }
}
