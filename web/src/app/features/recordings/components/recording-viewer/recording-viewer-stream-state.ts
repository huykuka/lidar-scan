export type ReadyAction = 'start' | 'eof' | 'ignore';

export function readyAction(frameCount: number, session: number, startedSession: number): ReadyAction {
  if (frameCount === 0) return 'eof';
  return startedSession === session ? 'ignore' : 'start';
}

export interface PointCloudGeometryTarget {
  visible: boolean;
  geometry?: {
    setDrawRange(start: number, count: number): void;
    attributes: Record<string, {needsUpdate: boolean} | undefined>;
  };
}

export function copyStreamedXyz(
  target: PointCloudGeometryTarget,
  destination: Float32Array,
  xyz: Float32Array,
  pointCount: number,
  maxPoints: number,
): number {
  const count = Math.min(Math.max(pointCount, 0), maxPoints, destination.length / 3, xyz.length / 3);
  destination.set(xyz.subarray(0, count * 3));
  fitPointCloudToView(destination, count);
  flushPointCloudGeometry(target, count);
  return count;
}

/** Keep arbitrary LiDAR world coordinates inside shared scene camera bounds. */
export function fitPointCloudToView(points: Float32Array, count: number): void {
  if (count <= 0) return;
  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (let i = 0; i < count * 3; i += 3) {
    const x = points[i], y = points[i + 1], z = points[i + 2];
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) continue;
    minX = Math.min(minX, x); minY = Math.min(minY, y); minZ = Math.min(minZ, z);
    maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); maxZ = Math.max(maxZ, z);
  }
  if (!Number.isFinite(minX)) return;
  const centerX = (minX + maxX) / 2, centerY = (minY + maxY) / 2, centerZ = (minZ + maxZ) / 2;
  const extent = Math.max(maxX - minX, maxY - minY, maxZ - minZ, 1);
  const scale = 8 / extent;
  for (let i = 0; i < count * 3; i += 3) {
    points[i] = (points[i] - centerX) * scale;
    points[i + 1] = (points[i + 1] - centerY) * scale;
    points[i + 2] = (points[i + 2] - centerZ) * scale;
  }
}

/** Flush bounded stream state into already-created Three.js geometry. */
export function flushPointCloudGeometry(target: PointCloudGeometryTarget, count: number): void {
  const safeCount = Math.max(0, count);
  target.visible = safeCount > 0;
  const geometry = target.geometry;
  if (!geometry) return;
  geometry.setDrawRange(0, safeCount);
  const position = geometry.attributes['position'];
  if (position) position.needsUpdate = true;
}
