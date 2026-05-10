/**
 * Reject toast — Spec 13 §7, §7.1.
 *
 * 便條 create 後若違反 gate，顯示 toast 提供：
 *   - 修改  → 開啟便條編輯
 *   - 丟棄  → 刪除草稿
 *   - 仍要送出  → force_publish=true（人類限定）
 */

import { useEffect, type CSSProperties } from 'react';

export interface RejectInfo {
  reasonZh: string;
  ruleModule: string;
  ruleName: string;
  matchedText?: string;
  draftId: string; // 便條草稿 id
}

interface RejectToastProps {
  info: RejectInfo | null;
  onEdit: (draftId: string) => void;
  onDiscard: (draftId: string) => void;
  onForcePublish: (draftId: string) => void;
  onDismiss: () => void;
  autoCloseMs?: number;
}

export function RejectToast({
  info,
  onEdit,
  onDiscard,
  onForcePublish,
  onDismiss,
  autoCloseMs = 10000,
}: RejectToastProps) {
  useEffect(() => {
    if (!info) return;
    const t = setTimeout(onDismiss, autoCloseMs);
    return () => clearTimeout(t);
  }, [info, autoCloseMs, onDismiss]);

  if (!info) return null;

  return (
    <div
      role="alertdialog"
      aria-live="assertive"
      style={{
        position: 'absolute',
        top: 16,
        left: '50%',
        transform: 'translateX(-50%)',
        background: '#fef3c7',
        border: '2px solid #d97706',
        borderRadius: '8px',
        padding: '12px 16px',
        zIndex: 1000,
        minWidth: '320px',
        maxWidth: '480px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        animation: 'title-drop 200ms ease-out',
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: '4px', color: '#92400e' }}>
        ⚠️ 便條格式不符
      </div>
      <div style={{ fontSize: '13px', color: '#451a03', whiteSpace: 'pre-wrap' }}>
        {info.reasonZh}
      </div>
      {info.matchedText && (
        <div style={{ fontSize: '12px', color: '#7c2d12', marginTop: '4px' }}>
          觸發詞：「{info.matchedText}」
        </div>
      )}
      <div style={{ display: 'flex', gap: '6px', marginTop: '10px', flexWrap: 'wrap' }}>
        <button
          onClick={() => onEdit(info.draftId)}
          style={btnStyle('#16a34a', '#fff')}
        >
          修改
        </button>
        <button
          onClick={() => onDiscard(info.draftId)}
          style={btnStyle('#6b7280', '#fff')}
        >
          丟棄
        </button>
        <button
          onClick={() => onForcePublish(info.draftId)}
          style={btnStyle('#dc2626', '#fff')}
          title="便條會被標記為違反規則 (gate_violation)"
        >
          仍要送出
        </button>
      </div>
    </div>
  );
}

function btnStyle(bg: string, fg: string): CSSProperties {
  return {
    background: bg,
    color: fg,
    border: 'none',
    padding: '6px 12px',
    borderRadius: '4px',
    fontSize: '13px',
    fontWeight: 600,
    cursor: 'pointer',
    minHeight: '36px',
  };
}
