import type {EChartsType} from 'echarts/core.js';

/** Resolve a Synergy design token (CSS custom property) to a colour ECharts can use. */
export function cssVar(name: string, fallback: string): string {
  try {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  } catch {
    return fallback;
  }
}

/** Minimal shape of the `<syn-chart>` element (a Lit element exposing its ECharts instance). */
export interface SynChartElement {
  updateComplete?: Promise<unknown>;
  getInstance(): EChartsType | undefined;
}

/** Wait for a `<syn-chart>` to create its ECharts instance, then hand it over. */
export async function withChartInstance(
  el: SynChartElement | undefined,
  use: (chart: EChartsType) => void,
): Promise<void> {
  if (!el) return;
  await el.updateComplete;
  const chart = el.getInstance();
  if (chart) use(chart);
}
