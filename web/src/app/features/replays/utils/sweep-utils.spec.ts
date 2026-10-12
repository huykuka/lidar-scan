import {PropertySchema} from '@core/models/node.model';
import {ReplayRun, RunScores, TargetScore} from '@core/models';
import {defaultRange, describeValues, isSweepable, MAX_SWEEP_RUNS, parseNumberList, plannedRuns, rangeValues} from './sweep-values';
import {commonMetrics, metricStats, sweptValue} from './run-metrics';
import {describeError, formatNumber, headlineTarget, scoreLabel, scoreVariant, signed} from './score-format';
import {buildSweepChart, ChartPoint, formatTick, niceTicks} from './sweep-chart-geometry';

describe('rangeValues', () => {
  it('builds an inclusive range without floating-point noise', () => {
    expect(rangeValues(0.1, 0.5, 0.1).values).toEqual([0.1, 0.2, 0.3, 0.4, 0.5]);
    expect(rangeValues(2, 10, 4).values).toEqual([2, 6, 10]);
  });

  it('includes the end only when the step lands on it', () => {
    expect(rangeValues(0, 1, 0.4).values).toEqual([0, 0.4, 0.8]);
  });

  it('supports a single value', () => {
    expect(rangeValues(3, 3, 1).values).toEqual([3]);
  });

  it('reports bad input instead of producing values', () => {
    expect(rangeValues(0, 1, 0).error).toMatch(/Step/);
    expect(rangeValues(0, 1, -1).error).toMatch(/Step/);
    expect(rangeValues(5, 1, 1).error).toMatch(/End/);
    expect(rangeValues(NaN, 1, 1).error).toMatch(/Enter/);
    expect(rangeValues(0, 1000, 1).error).toContain(String(MAX_SWEEP_RUNS));
  });
});

describe('parseNumberList', () => {
  it('splits on commas, spaces and semicolons and removes duplicates', () => {
    expect(parseNumberList('0.3, 0.5;1  0.5').values).toEqual([0.3, 0.5, 1]);
  });

  it('names the offending entry', () => {
    expect(parseNumberList('1, abc').error).toBe('"abc" is not a number');
    expect(parseNumberList('  ').error).toMatch(/at least one/);
  });
});

describe('describeValues / isSweepable', () => {
  it('lists few values and abbreviates many', () => {
    expect(describeValues([1, 2])).toBe('1, 2');
    expect(describeValues([0.3, 0.5, 0.7, 1, 1.5])).toBe('5 values: 0.3 … 1.5');
    expect(describeValues([])).toBe('no values');
    expect(describeValues(['a', true])).toBe('a, true');
  });

  it('only offers parameters with a numeric or enumerable domain', () => {
    const prop = (type: string, extra: Partial<PropertySchema> = {}) => ({name: 'p', label: 'P', type, ...extra}) as PropertySchema;
    expect(isSweepable(prop('number'))).toBe(true);
    expect(isSweepable(prop('boolean'))).toBe(true);
    expect(isSweepable(prop('select'))).toBe(true);
    expect(isSweepable(prop('vec3'))).toBe(false);
    expect(isSweepable(prop('string'))).toBe(false);
    expect(isSweepable(prop('number', {hidden: true}))).toBe(false);
    expect(isSweepable(prop('number', {name: 'throttle_ms'}))).toBe(false);
  });
});

const run = (id: string, nodes: Record<string, Record<string, number>>, extra: Partial<ReplayRun> = {}): ReplayRun =>
  ({
    id, label: id, status: 'completed', overrides: {},
    summary: {
      nodes: Object.fromEntries(
        Object.entries(nodes).map(([nid, values]) => [nid, {
          name: `Node ${nid}`, type: 't', emitted: 1, points_mean: 1,
          values: Object.fromEntries(Object.entries(values).map(([k, mean]) => [k, {count: 1, min: mean, max: mean, mean, last: mean}])),
        }]),
      ),
    },
    ...extra,
  }) as unknown as ReplayRun;

describe('commonMetrics', () => {
  it('keeps only metrics present in every completed run', () => {
    const a = run('a', {n1: {x: 1, y: 2}});
    const b = run('b', {n1: {x: 1}});
    expect(commonMetrics([a, b]).map((m) => m.key)).toEqual(['x']);
  });

  it('ignores runs that did not complete', () => {
    const failed = run('f', {}, {status: 'failed'});
    expect(commonMetrics([run('a', {n1: {x: 1}}), failed]).map((m) => m.key)).toEqual(['x']);
    expect(commonMetrics([failed])).toEqual([]);
  });

  it('folds metadata.* duplicates into the plain metric', () => {
    const r = run('a', {n1: {count: 1, 'metadata.count': 1, 'metadata.only': 2}});
    expect(commonMetrics([r]).map((m) => m.key)).toEqual(['count', 'metadata.only']);
  });

  it('reads stats and swept values', () => {
    const r = run('a', {n1: {x: 7}}, {overrides: {n1: {radius: 0.3}}});
    expect(metricStats(r, 'n1', 'x')?.mean).toBe(7);
    expect(metricStats(r, 'n1', 'zzz')).toBeNull();
    expect(sweptValue(r, 'n1', 'radius')).toBe(0.3);
    expect(sweptValue(r, 'n1', 'other')).toBeUndefined();
  });
});

const target = (extra: Partial<TargetScore>): TargetScore =>
  ({target_id: 't', label: 'L', node_id: 'n', metric_key: 'k', expected: 6, tolerance: 0.1, value: 6.05, std: 0.1, error: 0.05, abs_error: 0.05, pct_error: 0.8333, status: 'pass', ...extra}) as TargetScore;

describe('score formatting', () => {
  it('maps statuses to badge variants and labels', () => {
    expect(scoreVariant('pass')).toBe('success');
    expect(scoreVariant('fail')).toBe('danger');
    expect(scoreVariant('missing')).toBe('warning');
    expect(scoreVariant('info')).toBe('neutral');
    expect(scoreVariant(null)).toBe('neutral');
    expect(scoreLabel('missing')).toBe('No data');
    expect(scoreLabel(null)).toBe('');
  });

  it('formats numbers compactly', () => {
    expect(formatNumber(1.234567)).toBe('1.235');
    expect(formatNumber(12)).toBe('12');
    expect(formatNumber(null)).toBe('—');
    expect(formatNumber(NaN)).toBe('—');
    expect(signed(0.5)).toBe('+0.5');
    expect(signed(-0.5)).toBe('-0.5');
    expect(signed(0)).toBe('0');
  });

  it('describes the error with a percentage when it has one', () => {
    expect(describeError(target({}))).toBe('+0.05 (+0.833%)');
    expect(describeError(target({pct_error: null}))).toBe('+0.05');
    expect(describeError(target({error: null, status: 'missing'}))).toBe('no data');
  });

  it('shows the failing target first in a one-line summary', () => {
    const scores: RunScores = {overall: 'fail', targets: [target({}), target({target_id: 'x', status: 'fail'})]};
    expect(headlineTarget(scores)?.target_id).toBe('x');
    expect(headlineTarget({overall: null, targets: []})).toBeNull();
    expect(headlineTarget(null)).toBeNull();
  });
});

describe('niceTicks', () => {
  it('returns round values inside the range', () => {
    const ticks = niceTicks(0, 10, 5);
    expect(ticks).toEqual([0, 2, 4, 6, 8, 10]);
  });

  it('handles fractional and negative ranges', () => {
    expect(niceTicks(0.02, 0.18, 5)).toEqual([0.05, 0.1, 0.15]);
    expect(niceTicks(-1, 1, 5)).toEqual([-1, -0.5, 0, 0.5, 1]);
  });

  it('handles degenerate input', () => {
    expect(niceTicks(3, 3)).toEqual([3]);
    expect(niceTicks(NaN, 1)).toEqual([]);
    expect(formatTick(0.30000000000000004)).toBe('0.3');
  });
});

describe('buildSweepChart', () => {
  const opts = {width: 400, height: 200};
  const pts = (...xy: [number | string, number | null][]): ChartPoint[] =>
    xy.map(([x, y], i) => ({runId: `r${i}`, label: String(x), x, y, std: null, status: 'completed'}));

  it('places numeric x proportionally and sorts by x', () => {
    const c = buildSweepChart(pts([10, 1], [0, 2], [5, 3]), opts);
    expect(c.numericX).toBe(true);
    expect(c.plotted.map((p) => p.label)).toEqual(['0', '5', '10']);
    const [a, b, d] = c.plotted.map((p) => p.cx);
    expect(b - a).toBeCloseTo(d - b);
    expect(a).toBe(c.plot.left);
    expect(d).toBe(c.plot.right);
  });

  it('spaces non-numeric x evenly in the given order', () => {
    const c = buildSweepChart(pts(['a', 1], ['b', 2], ['c', 3]), opts);
    expect(c.numericX).toBe(false);
    expect(c.plotted.map((p) => p.label)).toEqual(['a', 'b', 'c']);
    expect(c.plotted[1].cx).toBeCloseTo((c.plot.left + c.plot.right) / 2);
  });

  it('puts larger values higher (smaller y)', () => {
    const c = buildSweepChart(pts([0, 1], [1, 9]), opts);
    expect(c.plotted[1].cy!).toBeLessThan(c.plotted[0].cy!);
  });

  it('draws the expected line and tolerance band inside the plot', () => {
    const c = buildSweepChart(pts([0, 5], [1, 7]), {...opts, expected: 6, tolerance: 0.5});
    expect(c.expectedY).not.toBeNull();
    expect(c.bandTop!).toBeLessThan(c.expectedY!);
    expect(c.bandBottom!).toBeGreaterThan(c.expectedY!);
    expect(c.bandTop!).toBeGreaterThanOrEqual(c.plot.top);
    expect(c.bandBottom!).toBeLessThanOrEqual(c.plot.bottom);
  });

  it('extends the y range to include the expected value', () => {
    const c = buildSweepChart(pts([0, 1], [1, 2]), {...opts, expected: 100});
    expect(c.expectedY!).toBeGreaterThanOrEqual(c.plot.top);
    expect(c.yTicks.some((t) => t.value >= 100)).toBe(true);
  });

  it('draws error bars only for points with a spread', () => {
    const points = pts([0, 5], [1, 5]);
    points[1].std = 1;
    const c = buildSweepChart(points, opts);
    expect(c.plotted[0].errTop).toBeNull();
    expect(c.plotted[1].errTop!).toBeLessThan(c.plotted[1].cy!);
  });

  it('skips runs without a value in the line but keeps their slot', () => {
    const c = buildSweepChart(pts([0, 1], [1, null], [2, 3]), opts);
    expect(c.plotted.length).toBe(3);
    expect(c.plotted[1].cy).toBeNull();
    expect(c.line.match(/L/g)?.length).toBe(1);
  });

  it('copes with one point, no points and a flat series', () => {
    const one = buildSweepChart(pts([4, 2]), opts);
    expect(one.plotted[0].cx).toBeCloseTo((one.plot.left + one.plot.right) / 2);
    expect(buildSweepChart([], opts).plotted).toEqual([]);
    const flat = buildSweepChart(pts([0, 3], [1, 3]), opts);
    expect(flat.plotted.every((p) => Number.isFinite(p.cy!))).toBe(true);
    expect(flat.line).not.toContain('NaN');
  });
});

describe('defaultRange', () => {
  it('spans half to one-and-a-half times the current value in five values', () => {
    const r = defaultRange(0.7);
    expect(r).toEqual({start: 0.35, end: 1.05, step: 0.175});
    expect(rangeValues(r.start, r.end, r.step).values.length).toBe(5);
  });

  it('accepts numeric strings (the saved config stores numbers as text)', () => {
    expect(defaultRange('50').start).toBe(25);
  });

  it('clamps to the parameter limits', () => {
    const r = defaultRange(10, {min: 8, max: 12});
    expect(r.start).toBe(8);
    expect(r.end).toBe(12);
  });

  it('falls back to 0..1 for zero or unknown values', () => {
    expect(defaultRange(0)).toEqual({start: 0, end: 1, step: 0.25});
    expect(defaultRange(undefined)).toEqual({start: 0, end: 1, step: 0.25});
  });

  it('never returns an empty range', () => {
    const r = defaultRange(5, {min: 20});
    expect(r.end).toBeGreaterThan(r.start);
  });
});

describe('plannedRuns', () => {
  it('adds the baseline only when the current value is not already swept', () => {
    expect(plannedRuns([1, 2, 3], 5, true)).toBe(4);
    expect(plannedRuns([1, 2, 5], 5, true)).toBe(3);
    expect(plannedRuns([1, 2, 5], '5', true)).toBe(3);
    expect(plannedRuns([1, 2, 3], 5, false)).toBe(3);
    expect(plannedRuns([1, 2, 3], undefined, true)).toBe(3);
  });
});
