/** Geometry of the compare charts (pure, shared by the component and its tests). */

export const CHART_W = 520;
export const CHART_H = 160;
export const CHART_PAD = 6;

/** Inverse of the x mapping in `buildPath`: chart-box fraction (0..1) to a frame number. */
export function frameAtFraction(fraction: number, firstFrame: number, lastFrame: number): number {
  const spanX = Math.max(lastFrame - firstFrame, 1);
  const x = Math.min(Math.max(fraction, 0), 1) * CHART_W;
  const t = (x - CHART_PAD) / (CHART_W - 2 * CHART_PAD);
  return Math.round(firstFrame + Math.min(Math.max(t, 0), 1) * spanX);
}

/** Build an SVG polyline path for one series, scaled into the chart box. */
export function buildPath(
  pts: {frame: number; v: number}[],
  x0: number,
  x1: number,
  min: number,
  max: number,
): string {
  const spanX = Math.max(x1 - x0, 1);
  const spanY = max - min || 1;
  return pts
    .map((p, i) => {
      const x = CHART_PAD + ((p.frame - x0) / spanX) * (CHART_W - 2 * CHART_PAD);
      const y = CHART_H - CHART_PAD - ((p.v - min) / spanY) * (CHART_H - 2 * CHART_PAD);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

