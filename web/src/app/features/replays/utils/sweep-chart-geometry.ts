/** Pure geometry for the sweep chart: metric (y) against the swept parameter (x). */

export interface ChartPoint {
  runId: string;
  label: string;
  /** Swept value: numbers are placed proportionally, anything else evenly in order. */
  x: number | string;
  y: number | null;
  std?: number | null;
  status: string;
}

export interface ChartOptions {
  width: number;
  height: number;
  /** left, right, top, bottom */
  padding?: {left: number; right: number; top: number; bottom: number};
  expected?: number | null;
  tolerance?: number | null;
}

export interface PlottedPoint {
  runId: string;
  label: string;
  status: string;
  cx: number;
  cy: number | null;
  errTop: number | null;
  errBottom: number | null;
  value: number | null;
}

export interface SweepChart {
  numericX: boolean;
  plotted: PlottedPoint[];
  line: string;
  yTicks: {value: number; y: number}[];
  xTicks: {label: string; x: number}[];
  expectedY: number | null;
  bandTop: number | null;
  bandBottom: number | null;
  plot: {left: number; right: number; top: number; bottom: number};
}

const DEFAULT_PADDING = {left: 56, right: 16, top: 16, bottom: 34};

/** "Nice" tick values (1, 2, 5 × 10ⁿ) covering [min, max]. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) return [min];
  const rawStep = (max - min) / Math.max(count - 1, 1);
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const norm = rawStep / magnitude;
  const step = (norm <= 1.5 ? 1 : norm <= 3 ? 2 : norm <= 7 ? 5 : 10) * magnitude;
  const first = Math.ceil(min / step - 1e-9) * step;
  const ticks: number[] = [];
  for (let v = first; v <= max + step * 1e-9; v += step) ticks.push(Number(v.toPrecision(12)));
  return ticks;
}

export function formatTick(value: number): string {
  return String(Number(value.toPrecision(6)));
}

export function buildSweepChart(points: ChartPoint[], opts: ChartOptions): SweepChart {
  const pad = opts.padding ?? DEFAULT_PADDING;
  const plot = {left: pad.left, right: opts.width - pad.right, top: pad.top, bottom: opts.height - pad.bottom};
  const numericX = points.length > 0 && points.every((p) => typeof p.x === 'number');

  // ── x positions ────────────────────────────────────────────────────────
  const ordered = numericX ? [...points].sort((a, b) => (a.x as number) - (b.x as number)) : points;
  const xs = ordered.map((p) => p.x as number);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const xAt = (p: ChartPoint, index: number): number => {
    const inner = plot.right - plot.left;
    if (ordered.length === 1) return plot.left + inner / 2;
    if (numericX) return plot.left + (((p.x as number) - xMin) / (xMax - xMin || 1)) * inner;
    return plot.left + (index / (ordered.length - 1)) * inner;
  };

  // ── y domain ───────────────────────────────────────────────────────────
  const ys: number[] = [];
  for (const p of ordered) {
    if (p.y === null) continue;
    ys.push(p.y);
    if (p.std) ys.push(p.y - p.std, p.y + p.std);
  }
  const expected = opts.expected ?? null;
  if (expected !== null) {
    ys.push(expected);
    if (opts.tolerance) ys.push(expected - opts.tolerance, expected + opts.tolerance);
  }
  let yMin = ys.length ? Math.min(...ys) : 0;
  let yMax = ys.length ? Math.max(...ys) : 1;
  if (yMin === yMax) {
    yMin -= 1;
    yMax += 1;
  }
  const margin = (yMax - yMin) * 0.08;
  yMin -= margin;
  yMax += margin;
  const yAt = (v: number): number => plot.bottom - ((v - yMin) / (yMax - yMin)) * (plot.bottom - plot.top);

  // ── shapes ─────────────────────────────────────────────────────────────
  const plotted: PlottedPoint[] = ordered.map((p, i) => ({
    runId: p.runId,
    label: p.label,
    status: p.status,
    cx: xAt(p, i),
    cy: p.y === null ? null : yAt(p.y),
    errTop: p.y === null || !p.std ? null : yAt(p.y + p.std),
    errBottom: p.y === null || !p.std ? null : yAt(p.y - p.std),
    value: p.y,
  }));
  const line = plotted
    .filter((p) => p.cy !== null)
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.cx.toFixed(1)},${p.cy!.toFixed(1)}`)
    .join(' ');

  const hasExpected = expected !== null;
  return {
    numericX,
    plotted,
    line,
    yTicks: niceTicks(yMin, yMax).map((value) => ({value, y: yAt(value)})),
    xTicks: ordered.map((p, i) => ({label: typeof p.x === 'number' ? formatTick(p.x) : String(p.x), x: xAt(p, i)})),
    expectedY: hasExpected ? yAt(expected) : null,
    bandTop: hasExpected && opts.tolerance ? yAt(expected + opts.tolerance) : null,
    bandBottom: hasExpected && opts.tolerance ? yAt(expected - opts.tolerance) : null,
    plot,
  };
}
