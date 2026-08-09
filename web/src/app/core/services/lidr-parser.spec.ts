import {parseJsonPointCloud, parseLidrFrame} from './lidr-parser';

function frameBuffer(count = 2): ArrayBuffer {
  const buffer = new ArrayBuffer(28 + count * 12);
  const view = new DataView(buffer);
  new Uint8Array(buffer, 0, 4).set([76, 73, 68, 82]);
  view.setUint32(4, 2, true);
  view.setUint32(8, 4, true);
  view.setUint32(12, 1250, true);
  view.setFloat64(16, 123.5, true);
  view.setUint32(24, count, true);
  new Float32Array(buffer, 28).set([1, 2, 3, 4, 5, 6].slice(0, count * 3));
  return buffer;
}

describe('parseLidrFrame', () => {
  it('parses v2 frame header and xyz payload', () => {
    const result = parseLidrFrame(frameBuffer());
    expect(result).toMatchObject({type: 'frame', generation: 4, frameIndex: 1250, timestamp: 123.5, pointCount: 2});
    expect(result.type === 'frame' && [...result.xyz]).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it.each([
    ['short header', new ArrayBuffer(4)],
    ['wrong magic', (() => { const b = frameBuffer(); new Uint8Array(b)[0] = 65; return b; })()],
    ['wrong version', (() => { const b = frameBuffer(); new DataView(b).setUint32(4, 1, true); return b; })()],
    ['wrong payload length', (() => frameBuffer(1).slice(0, 28 + 12 - 1))()],
  ])('returns invalid_frame for %s', (_, buffer) => {
    expect(parseLidrFrame(buffer)).toMatchObject({type: 'error', code: 'invalid_frame'});
  });
});

describe('parseJsonPointCloud', () => {
  it('keeps legacy JSON shapes', () => {
    const points = [[1, 2, 3]];
    expect(parseJsonPointCloud({data: {points}})).toBe(points);
    expect(parseJsonPointCloud(null)).toBeNull();
  });
});
