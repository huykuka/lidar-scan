import {buildPath, CHART_PAD, CHART_W, frameAtFraction} from './chart-geometry';

describe('buildPath', () => {
  it('starts with M and connects points with L', () => {
    const d = buildPath(
      [{frame: 0, v: 0}, {frame: 5, v: 5}, {frame: 10, v: 10}],
      0, 10, 0, 10,
    );
    expect(d.startsWith('M')).toBe(true);
    expect(d.match(/L/g)?.length).toBe(2);
  });

  it('puts the minimum at the bottom and maximum at the top of the box', () => {
    const d = buildPath([{frame: 0, v: 0}, {frame: 1, v: 1}], 0, 1, 0, 1);
    const ys = [...d.matchAll(/,(-?[\d.]+)/g)].map((m) => Number(m[1]));
    expect(ys[0]).toBeGreaterThan(ys[1]); // SVG y grows downward
  });

  it('does not produce NaN for a flat series', () => {
    const d = buildPath([{frame: 3, v: 7}, {frame: 3, v: 7}], 3, 3, 7, 7);
    expect(d).not.toContain('NaN');
  });
});

describe('frameAtFraction', () => {
  it('maps the chart edges to the first and last frame', () => {
    expect(frameAtFraction(0, 100, 200)).toBe(100);
    expect(frameAtFraction(1, 100, 200)).toBe(200);
  });

  it('maps the middle of the plotted area to the middle frame', () => {
    expect(frameAtFraction(0.5, 0, 100)).toBe(50);
  });

  it('is the inverse of the x mapping used by buildPath', () => {
    const [first, last] = [10, 510];
    const frame = 321;
    const x = CHART_PAD + ((frame - first) / (last - first)) * (CHART_W - 2 * CHART_PAD);
    expect(frameAtFraction(x / CHART_W, first, last)).toBe(frame);
  });

  it('clamps clicks outside the range and survives a single-frame series', () => {
    expect(frameAtFraction(-1, 5, 50)).toBe(5);
    expect(frameAtFraction(2, 5, 50)).toBe(50);
    expect(Number.isFinite(frameAtFraction(0.5, 7, 7))).toBe(true);
  });
});
