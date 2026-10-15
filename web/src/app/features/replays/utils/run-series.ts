import {CapturedFrame, ReplayOutputs} from '@core/models';

/** Pseudo-key for the number of points a node emitted per frame. */
export const POINTS_KEY = '__points__';

export interface SeriesPoint {
  frame: number;
  value: number;
}

export function seriesLabel(key: string): string {
  return key === POINTS_KEY ? 'point count' : key;
}

/** Numeric value of one record, or null when it has none. */
function pick(record: CapturedFrame, key: string): number | null {
  const raw = key === POINTS_KEY ? record.points : record.values[key];
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : null;
}

/**
 * One value of one node over the frames. A node may emit several times per frame; the last
 * emission wins, as in the run comparison.
 */
export function buildSeries(outputs: ReplayOutputs | null, nodeId: string, key: string): SeriesPoint[] {
  const frames = outputs?.nodes[nodeId]?.frames ?? [];
  const byFrame = new Map<number, number>();
  for (const record of frames) {
    const value = pick(record, key);
    if (value !== null) byFrame.set(record.frame, value);
  }
  return [...byFrame.entries()].sort((a, b) => a[0] - b[0]).map(([frame, value]) => ({frame, value}));
}

/** Frames where the series changes by more than `factor` x its typical (median) step. */
export function findJumps(points: SeriesPoint[], factor = 5, limit = 5): SeriesPoint[] {
  if (points.length < 3) return [];
  const steps = points.slice(1).map((p, i) => Math.abs(p.value - points[i].value));
  const median = [...steps].sort((a, b) => a - b)[Math.floor(steps.length / 2)];
  const threshold = Math.max(median * factor, 1e-9);
  return points
    .slice(1)
    .map((p, i) => ({p, step: steps[i]}))
    .filter((x) => x.step > threshold)
    .sort((a, b) => b.step - a.step)
    .slice(0, limit)
    .map((x) => x.p)
    .sort((a, b) => a.frame - b.frame);
}
