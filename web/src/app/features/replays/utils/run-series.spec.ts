import {describe, expect, it} from 'vitest';
import {ReplayOutputs} from '@core/models';
import {buildSeries, findJumps, POINTS_KEY} from './run-series';

const outputs: ReplayOutputs = {
  nodes: {
    n1: {
      name: 'Filter',
      type: 'filter',
      frames: [
        {frame: 1, timestamp: null, points: 10, values: {count: 5, label: 'x'}},
        {frame: 0, timestamp: null, points: 8, values: {count: 4}},
        {frame: 1, timestamp: null, points: 12, values: {count: 6}},
        {frame: 2, timestamp: null, points: null, values: {count: NaN}},
      ],
    },
  },
  saved_results: [],
  errors: [],
};

describe('buildSeries', () => {
  it('sorts by frame and keeps the last emission per frame', () => {
    expect(buildSeries(outputs, 'n1', 'count')).toEqual([
      {frame: 0, value: 4},
      {frame: 1, value: 6},
    ]);
  });

  it('reads point counts through the pseudo key', () => {
    expect(buildSeries(outputs, 'n1', POINTS_KEY).map((p) => p.value)).toEqual([8, 12]);
  });

  it('skips non-numeric values and unknown nodes', () => {
    expect(buildSeries(outputs, 'n1', 'label')).toEqual([]);
    expect(buildSeries(outputs, 'nope', 'count')).toEqual([]);
    expect(buildSeries(null, 'n1', 'count')).toEqual([]);
  });
});

describe('findJumps', () => {
  it('flags a sudden step against a quiet series', () => {
    const pts = [1, 1.1, 1, 1.1, 9, 9.1].map((value, frame) => ({frame, value}));
    expect(findJumps(pts).map((p) => p.frame)).toEqual([4]);
  });

  it('finds nothing in a steady series or a short one', () => {
    expect(findJumps([1, 2, 3, 4, 5].map((value, frame) => ({frame, value})))).toEqual([]);
    expect(findJumps([{frame: 0, value: 1}])).toEqual([]);
  });
});
