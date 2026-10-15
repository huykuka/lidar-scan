import {ReplayOutputs} from '@core/models';
import {buildSeries, POINTS_KEY, SeriesPoint, seriesLabel} from './run-series';

export interface CategoryKey {
  nodeId: string;
  key: string;
}

export interface ValueShare {
  value: string;
  count: number;
  percent: number;
  firstFrame: number;
  lastFrame: number;
}

export interface SnapshotEntry {
  key: string;
  value: unknown;
}

export interface NodeSnapshot {
  nodeId: string;
  name: string;
  type: string;
  points: number | null;
  /** Several emissions in one frame are shown as separate records. */
  entries: SnapshotEntry[];
}

const isNumber = (v: unknown): boolean => typeof v === 'number' && Number.isFinite(v);

/**
 * Keys whose values are text, true/false or empty at least once (the numeric ones are charted).
 * `metadata.x` mirrors `x` in many nodes, so the mirror is dropped.
 */
export function categoryKeys(outputs: ReplayOutputs | null): CategoryKey[] {
  const out: CategoryKey[] = [];
  for (const [nodeId, node] of Object.entries(outputs?.nodes ?? {})) {
    const seen = new Map<string, boolean>(); // key -> has a non-numeric value
    for (const rec of node.frames) {
      for (const [key, value] of Object.entries(rec.values)) {
        seen.set(key, (seen.get(key) ?? false) || !isNumber(value));
      }
    }
    for (const [key, nonNumeric] of seen) {
      if (!nonNumeric) continue;
      if (key.startsWith('metadata.') && seen.has(key.slice(9))) continue;
      out.push({nodeId, key});
    }
  }
  return out;
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(6)));
  return String(value);
}

/** How often each value of one key occurs, most common first. */
export function distribution(outputs: ReplayOutputs | null, nodeId: string, key: string, limit = 20): ValueShare[] {
  const frames = outputs?.nodes[nodeId]?.frames ?? [];
  const seen = new Map<string, ValueShare>();
  let total = 0;
  for (const rec of frames) {
    if (!(key in rec.values)) continue;
    total++;
    const text = formatValue(rec.values[key]);
    const share = seen.get(text);
    if (share) {
      share.count++;
      share.lastFrame = rec.frame;
    } else {
      seen.set(text, {value: text, count: 1, percent: 0, firstFrame: rec.frame, lastFrame: rec.frame});
    }
  }
  return [...seen.values()]
    .map((s) => ({...s, percent: total ? (s.count / total) * 100 : 0}))
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}

/** First and last frame that any node produced output for. */
export function frameRange(outputs: ReplayOutputs | null): {min: number; max: number} | null {
  let min = Infinity;
  let max = -Infinity;
  for (const node of Object.values(outputs?.nodes ?? {})) {
    for (const rec of node.frames) {
      if (rec.frame < min) min = rec.frame;
      if (rec.frame > max) max = rec.frame;
    }
  }
  return Number.isFinite(min) ? {min, max} : null;
}

/** Everything every node emitted for one frame (all metadata, not only numbers). */
export function frameSnapshot(outputs: ReplayOutputs | null, frame: number): NodeSnapshot[] {
  const out: NodeSnapshot[] = [];
  for (const [nodeId, node] of Object.entries(outputs?.nodes ?? {})) {
    const records = node.frames.filter((r) => r.frame === frame);
    if (records.length === 0) continue;
    const last = records[records.length - 1];
    const keys = Object.keys(last.values);
    out.push({
      nodeId,
      name: node.name,
      type: node.type,
      points: last.points,
      entries: keys
        .filter((k) => !(k.startsWith('metadata.') && keys.includes(k.slice(9))))
        .map((key) => ({key, value: last.values[key]})),
    });
  }
  return out;
}

export interface NumericChart {
  key: string;
  label: string;
  points: SeriesPoint[];
  min: number;
  max: number;
  mean: number;
  std: number;
  firstFrame: number;
  lastFrame: number;
}

export interface CategoryInfo {
  key: string;
  shares: ValueShare[];
}

export interface NodeMetrics {
  numeric: NumericChart[];
  category: CategoryInfo[];
}

/** Every metadata field one node emitted: numbers as chartable series, the rest as value counts. */
export function nodeMetrics(outputs: ReplayOutputs | null, nodeId: string): NodeMetrics {
  const frames = outputs?.nodes[nodeId]?.frames ?? [];
  const keys = new Set<string>();
  for (const rec of frames) for (const k of Object.keys(rec.values)) keys.add(k);

  const numericKeys = [POINTS_KEY, ...[...keys].filter((k) => !(k.startsWith('metadata.') && keys.has(k.slice(9))))];
  const numeric: NumericChart[] = [];
  const category: CategoryInfo[] = [];
  for (const key of numericKeys) {
    const points = buildSeries(outputs, nodeId, key);
    if (points.length > 0) {
      const values = points.map((p) => p.value);
      const mean = values.reduce((a, b) => a + b, 0) / values.length;
      numeric.push({
        key,
        label: seriesLabel(key),
        points,
        min: Math.min(...values),
        max: Math.max(...values),
        mean,
        std: Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length),
        firstFrame: points[0].frame,
        lastFrame: points[points.length - 1].frame,
      });
    } else if (key !== POINTS_KEY) {
      category.push({key, shares: distribution(outputs, nodeId, key, 8)});
    }
  }
  return {numeric, category};
}
