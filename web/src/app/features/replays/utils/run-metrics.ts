import {ReplayRun, ValueStats} from '@core/models';

export interface MetricOption {
  nodeId: string;
  nodeName: string;
  key: string;
}

/**
 * Metrics (node + value name) present in every given run. Raw duplicates produced by the
 * pipeline (``metadata.x`` mirroring ``x``) are folded into the shorter name.
 */
export function commonMetrics(runs: ReplayRun[]): MetricOption[] {
  const completed = runs.filter((r) => r.status === 'completed' && r.summary?.nodes);
  if (completed.length === 0) return [];
  const [first, ...rest] = completed;
  const out: MetricOption[] = [];
  for (const [nodeId, node] of Object.entries(first.summary.nodes ?? {})) {
    for (const key of Object.keys(node.values)) {
      if (!rest.every((r) => r.summary.nodes?.[nodeId]?.values?.[key])) continue;
      out.push({nodeId, nodeName: node.name, key});
    }
  }
  const keys = new Set(out.map((m) => `${m.nodeId}|${m.key}`));
  return out.filter((m) => !(m.key.startsWith('metadata.') && keys.has(`${m.nodeId}|${m.key.slice(9)}`)));
}

export function metricStats(run: ReplayRun, nodeId: string, key: string): ValueStats | null {
  return run.summary?.nodes?.[nodeId]?.values?.[key] ?? null;
}

/** The sweep's overridden value for one run (the single override of a sweep run). */
export function sweptValue(run: ReplayRun, nodeId: string, parameter: string): unknown {
  return run.overrides?.[nodeId]?.[parameter];
}

/** Every metric seen in any completed run (used to pick what a ground-truth target measures). */
export function allMetrics(runs: ReplayRun[]): MetricOption[] {
  const seen = new Map<string, MetricOption>();
  for (const run of runs) {
    if (run.status !== 'completed') continue;
    for (const [nodeId, node] of Object.entries(run.summary?.nodes ?? {})) {
      for (const key of Object.keys(node.values)) {
        const id = `${nodeId}|${key}`;
        if (!seen.has(id)) seen.set(id, {nodeId, nodeName: node.name, key});
      }
    }
  }
  const all = [...seen.values()];
  return all.filter((m) => !(m.key.startsWith('metadata.') && seen.has(`${m.nodeId}|${m.key.slice(9)}`)));
}

/** Stats of one metric from the most recent completed run that has it. */
export function latestMetricStats(runs: ReplayRun[], nodeId: string, key: string): ValueStats | null {
  const sorted = [...runs].filter((r) => r.status === 'completed').sort((a, b) => b.created_at.localeCompare(a.created_at));
  for (const run of sorted) {
    const stats = metricStats(run, nodeId, key);
    if (stats) return stats;
  }
  return null;
}
