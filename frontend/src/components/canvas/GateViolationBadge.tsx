/**
 * Gate violation badge — Spec 13 §7.1.
 *
 * 強制送出的便條右下角 ⚠️ icon，hover/tap 顯示違反規則。
 */

import { useState } from 'react';

export interface GateViolationMeta {
  phase: string;
  zone_id?: string;
  rule: string;
  module: string;
  matched_text?: string;
}

interface GateViolationBadgeProps {
  violation: GateViolationMeta;
}

export function GateViolationBadge({ violation }: GateViolationBadgeProps) {
  const [visible, setVisible] = useState(false);

  return (
    <div
      style={{
        position: 'absolute',
        right: 4,
        bottom: 4,
        cursor: 'help',
      }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onClick={() => setVisible((v) => !v)}
      role="tooltip"
      aria-label={`違反規則：${violation.rule}`}
    >
      <span style={{ fontSize: '14px', color: '#dc2626' }}>⚠️</span>
      {visible && (
        <div
          style={{
            position: 'absolute',
            bottom: '22px',
            right: 0,
            background: '#fef3c7',
            border: '1px solid #d97706',
            borderRadius: '4px',
            padding: '6px 8px',
            fontSize: '11px',
            whiteSpace: 'nowrap',
            zIndex: 10,
            boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
            color: '#7c2d12',
          }}
        >
          <div>違反：{violation.rule}</div>
          <div>階段：{violation.phase}</div>
          {violation.matched_text && <div>觸發詞：「{violation.matched_text}」</div>}
        </div>
      )}
    </div>
  );
}
