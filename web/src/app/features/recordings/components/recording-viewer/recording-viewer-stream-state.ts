export type ReadyAction = 'start' | 'eof' | 'ignore';
export type PlaybackAction = 'start' | 'pause';

export function readyAction(frameCount: number, session: number, startedSession: number): ReadyAction {
  if (frameCount === 0) return 'eof';
  return startedSession === session ? 'ignore' : 'start';
}

export function playbackAction(isPlaying: boolean): PlaybackAction {
  return isPlaying ? 'pause' : 'start';
}

export function nextFrameIndex(frameIndex: number, frameCount: number): number {
  return Math.min(frameIndex + 1, Math.max(frameCount - 1, 0));
}

export function shouldApplyFrame(
  isPlaying: boolean,
  generation: number,
  latestGeneration: number,
  pendingSeekGeneration: number | null = null,
): boolean {
  return generation === latestGeneration && (isPlaying || generation === pendingSeekGeneration);
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
  flushPointCloudGeometry(target, count);
  return count;
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
