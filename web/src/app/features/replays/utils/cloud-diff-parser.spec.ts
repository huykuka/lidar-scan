import {parseCloudDiff, splitDiffLayers} from './cloud-diff-parser';

/** Build a payload exactly like the backend `pack_cloud_diff`. */
function pack(a: number[][], flagsA: number[], b: number[][], flagsB: number[]): ArrayBuffer {
  const pad4 = (n: number) => (4 - (n % 4)) % 4;
  const size = 32 + a.length * 12 + a.length + pad4(a.length) + b.length * 12 + b.length + pad4(b.length);
  const buf = new ArrayBuffer(size);
  const view = new DataView(buf);
  view.setUint32(0, a.length, true);
  view.setUint32(4, b.length, true);
  view.setUint32(8, flagsA.filter(Boolean).length, true);
  view.setUint32(12, flagsB.filter(Boolean).length, true);
  view.setFloat32(16, 0.5, true);
  view.setFloat32(20, 0.25, true);
  let off = 32;
  new Float32Array(buf, off, a.length * 3).set(a.flat());
  off += a.length * 12;
  new Uint8Array(buf, off, a.length).set(flagsA);
  off += a.length + pad4(a.length);
  new Float32Array(buf, off, b.length * 3).set(b.flat());
  off += b.length * 12;
  new Uint8Array(buf, off, b.length).set(flagsB);
  return buf;
}

describe('parseCloudDiff', () => {
  const a = [[0, 0, 0], [1, 1, 1], [2, 2, 2]]; // 3 flags -> 1 byte padding
  const b = [[0, 0, 0], [9, 9, 9]];             // 2 flags -> 2 bytes padding

  it('decodes header, coordinates and flags with padding', () => {
    const d = parseCloudDiff(pack(a, [0, 0, 1], b, [0, 1]));
    expect([d.countA, d.countB, d.onlyA, d.onlyB]).toEqual([3, 2, 1, 1]);
    expect(d.meanDistA).toBeCloseTo(0.5);
    expect(d.meanDistB).toBeCloseTo(0.25);
    expect(Array.from(d.xyzA)).toEqual(a.flat());
    expect(Array.from(d.flagsA)).toEqual([0, 0, 1]);
    expect(Array.from(d.xyzB)).toEqual(b.flat());
    expect(Array.from(d.flagsB)).toEqual([0, 1]);
  });

  it('rejects truncated or malformed payloads', () => {
    expect(() => parseCloudDiff(new ArrayBuffer(8))).toThrow();
    const ok = pack(a, [0, 0, 1], b, [0, 1]);
    expect(() => parseCloudDiff(ok.slice(0, ok.byteLength - 4))).toThrow();
  });

  it('handles empty clouds', () => {
    const d = parseCloudDiff(pack([], [], [], []));
    expect([d.countA, d.countB]).toEqual([0, 0]);
  });
});

describe('splitDiffLayers', () => {
  it('routes points to matched / only-A / only-B layers', () => {
    const d = parseCloudDiff(pack([[0, 0, 0], [1, 1, 1], [2, 2, 2]], [0, 0, 1], [[0, 0, 0], [9, 9, 9]], [0, 1]));
    const matched = new Float32Array(9);
    const onlyA = new Float32Array(9);
    const onlyB = new Float32Array(9);
    expect(splitDiffLayers(d, matched, onlyA, onlyB)).toEqual({matched: 2, onlyA: 1, onlyB: 1});
    expect(Array.from(matched.subarray(0, 6))).toEqual([0, 0, 0, 1, 1, 1]);
    expect(Array.from(onlyA.subarray(0, 3))).toEqual([2, 2, 2]);
    expect(Array.from(onlyB.subarray(0, 3))).toEqual([9, 9, 9]);
  });

  it('never writes past a layer capacity', () => {
    const d = parseCloudDiff(pack([[0, 0, 0], [1, 1, 1]], [0, 0], [], []));
    const matched = new Float32Array(3); // room for one point
    const r = splitDiffLayers(d, matched, new Float32Array(3), new Float32Array(3));
    expect(r.matched).toBe(1);
  });
});
