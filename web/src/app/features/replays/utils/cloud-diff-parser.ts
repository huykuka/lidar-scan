/** Decoder for `GET /replays/compare/cloud` (see backend `pack_cloud_diff`). */

const HEADER_BYTES = 32;

export interface CloudDiff {
  countA: number;
  countB: number;
  /** Points of A without a counterpart in B within the tolerance. */
  onlyA: number;
  /** Points of B without a counterpart in A within the tolerance. */
  onlyB: number;
  meanDistA: number;
  meanDistB: number;
  xyzA: Float32Array;
  flagsA: Uint8Array;
  xyzB: Float32Array;
  flagsB: Uint8Array;
}

export function parseCloudDiff(buffer: ArrayBuffer): CloudDiff {
  if (buffer.byteLength < HEADER_BYTES) {
    throw new Error('Cloud diff payload is too short');
  }
  const view = new DataView(buffer);
  const countA = view.getUint32(0, true);
  const countB = view.getUint32(4, true);
  const onlyA = view.getUint32(8, true);
  const onlyB = view.getUint32(12, true);
  const meanDistA = view.getFloat32(16, true);
  const meanDistB = view.getFloat32(20, true);

  const pad4 = (n: number) => (4 - (n % 4)) % 4;
  const expected = HEADER_BYTES + countA * 12 + countA + pad4(countA) + countB * 12 + countB + pad4(countB);
  if (buffer.byteLength !== expected) {
    throw new Error(`Cloud diff payload has ${buffer.byteLength} bytes, expected ${expected}`);
  }

  let offset = HEADER_BYTES;
  const xyzA = new Float32Array(buffer, offset, countA * 3);
  offset += countA * 12;
  const flagsA = new Uint8Array(buffer, offset, countA);
  offset += countA + pad4(countA);
  const xyzB = new Float32Array(buffer, offset, countB * 3);
  offset += countB * 12;
  const flagsB = new Uint8Array(buffer, offset, countB);

  return {countA, countB, onlyA, onlyB, meanDistA, meanDistB, xyzA, flagsA, xyzB, flagsB};
}

export interface DiffLayers {
  /** Points present (within tolerance) in both runs — taken from A. */
  matched: number;
  onlyA: number;
  onlyB: number;
}

/**
 * Split a diff into three destination buffers (matched / only-A / only-B).
 * Each destination is filled from index 0 and capped at its own capacity.
 */
export function splitDiffLayers(
  diff: CloudDiff,
  matched: Float32Array,
  onlyA: Float32Array,
  onlyB: Float32Array,
): DiffLayers {
  let m = 0;
  let a = 0;
  let b = 0;
  const capM = matched.length / 3;
  const capA = onlyA.length / 3;
  const capB = onlyB.length / 3;

  for (let i = 0; i < diff.countA; i++) {
    const src = i * 3;
    if (diff.flagsA[i]) {
      if (a < capA) onlyA.set(diff.xyzA.subarray(src, src + 3), a++ * 3);
    } else if (m < capM) {
      matched.set(diff.xyzA.subarray(src, src + 3), m++ * 3);
    }
  }
  for (let i = 0; i < diff.countB; i++) {
    if (diff.flagsB[i] && b < capB) {
      const src = i * 3;
      onlyB.set(diff.xyzB.subarray(src, src + 3), b++ * 3);
    }
  }
  return {matched: m, onlyA: a, onlyB: b};
}
