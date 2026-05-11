/**
 * ZoneOverlay — Spec 13 §2.2.
 *
 * 渲染所有 active zones 的 dashed 外框 + Pink 標題便條，
 * 跟著 tldraw camera 同步縮放與平移。
 */

import { useEffect, useMemo, useState } from 'react';
import { useZonesStore, type ZoneState } from '@/stores/zonesStore';

interface ZoneOverlayProps {
  cameraX: number;
  cameraY: number;
  cameraZ: number;
}

export function ZoneOverlay({ cameraX, cameraY, cameraZ }: ZoneOverlayProps) {
  const zones = useZonesStore((s) => s.zones);

  const zoneList = useMemo(() => Object.values(zones), [zones]);

  if (zoneList.length === 0) return null;

  return (
    <div className="zone-overlay-container" aria-hidden="true">
      {zoneList.map((zone) => (
        <ZoneFrame
          key={zone.id}
          zone={zone}
          cameraX={cameraX}
          cameraY={cameraY}
          cameraZ={cameraZ}
        />
      ))}
    </div>
  );
}

function ZoneFrame({
  zone,
  cameraX,
  cameraY,
  cameraZ,
}: {
  zone: ZoneState;
  cameraX: number;
  cameraY: number;
  cameraZ: number;
}) {
  const [animating, setAnimating] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => setAnimating(false), 350);
    return () => clearTimeout(t);
  }, [zone.drawnAt]);

  const screenX = (zone.bounds.x + cameraX) * cameraZ;
  const screenY = (zone.bounds.y + cameraY) * cameraZ;
  const screenW = zone.bounds.w * cameraZ;
  const screenH = zone.bounds.h * cameraZ;

  const className = [
    'zone-overlay',
    `zone-overlay--${zone.visual.frame_shape}`,
    zone.active ? '' : 'zone-overlay--inactive',
    animating ? 'zone-overlay--drawing' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={className}
      style={{
        left: `${screenX}px`,
        top: `${screenY}px`,
        width: `${screenW}px`,
        height: `${screenH}px`,
        borderColor: zone.visual.border_color,
      }}
    >
      {zone.visual.title_sticky && (
        <div
          className={
            'zone-overlay__title' +
            (animating ? ' zone-title-sticky--drawing' : '')
          }
        >
          {zone.visual.title_sticky}
        </div>
      )}
    </div>
  );
}
