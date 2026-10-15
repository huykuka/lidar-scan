import {describe, expect, it} from 'vitest';
import {ReplayOutputs} from '@core/models';
import {categoryKeys, distribution, formatValue, frameRange, frameSnapshot, nodeMetrics} from './run-metadata';

const rec = (frame: number, values: Record<string, unknown>, points: number | null = 1) => ({frame, timestamp: null, points, values});

const outputs: ReplayOutputs = {
  nodes: {
    a: {
      name: 'Crop', type: 'crop',
      frames: [
        rec(0, {count: 1, 'metadata.count': 1, who: 'x', flag: true}),
        rec(1, {count: 2, 'metadata.count': 2, who: 'x', flag: false}),
        rec(2, {count: 3, 'metadata.count': 3, who: 'y', flag: false}),
      ],
    },
    b: {name: 'Merge', type: 'fusion', frames: [rec(1, {}), rec(1, {}, 9)]},
  },
  saved_results: [],
  errors: [],
};

describe('categoryKeys', () => {
  it('lists text and boolean keys, not numeric ones or their metadata mirrors', () => {
    expect(categoryKeys(outputs)).toEqual([{nodeId: 'a', key: 'who'}, {nodeId: 'a', key: 'flag'}]);
  });
  it('copes with no outputs', () => expect(categoryKeys(null)).toEqual([]));
});

describe('distribution', () => {
  it('counts each value with its share and frame span', () => {
    const d = distribution(outputs, 'a', 'who');
    expect(d.map((s) => [s.value, s.count, Math.round(s.percent)])).toEqual([['x', 2, 67], ['y', 1, 33]]);
    expect([d[0].firstFrame, d[0].lastFrame]).toEqual([0, 1]);
  });
  it('shows booleans as text', () => expect(distribution(outputs, 'a', 'flag').map((s) => s.value)).toEqual(['false', 'true']));
});

describe('frameRange / frameSnapshot', () => {
  it('spans every node', () => expect(frameRange(outputs)).toEqual({min: 0, max: 2}));
  it('returns only nodes that emitted at that frame, last emission winning', () => {
    const snap = frameSnapshot(outputs, 1);
    expect(snap.map((s) => s.nodeId)).toEqual(['a', 'b']);
    expect(snap[0].entries.map((e) => e.key)).toEqual(['count', 'who', 'flag']);
    expect(snap[1].points).toBe(9);
    expect(frameSnapshot(outputs, 0).map((s) => s.nodeId)).toEqual(['a']);
  });
  it('formats values', () => {
    expect([formatValue(null), formatValue(0.123456789), formatValue(3), formatValue(false)]).toEqual(['—', '0.123457', '3', 'false']);
  });
});

describe('nodeMetrics', () => {
  it('splits a node into numeric charts and text/boolean fields, folding metadata mirrors', () => {
    const m = nodeMetrics(outputs, 'a');
    expect(m.numeric.map((c) => c.key)).toEqual(['__points__', 'count']);
    expect(m.category.map((c) => c.key)).toEqual(['who', 'flag']);
    const count = m.numeric[1];
    expect([count.min, count.max, count.mean, count.firstFrame, count.lastFrame]).toEqual([1, 3, 2, 0, 2]);
  });
  it('is empty for an unknown node', () => expect(nodeMetrics(outputs, 'zzz')).toEqual({numeric: [], category: []}));
});
