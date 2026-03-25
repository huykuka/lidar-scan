/**
 * Pure utility functions for parsing LIDR binary WebSocket frames
 * and JSON point cloud payloads.
 *
 * These functions have zero side effects and no Angular injections —
 * they can be used in any context (services, workers, tests).
 */

export interface FramePayload {
  /** Unix timestamp in seconds (from LIDR header) */
  timestamp: number;
  /** Number of valid points in the `points` array */
  count: number;
  /** Flat [x0,y0,z0, x1,y1,z1, ...] in LiDAR coordinate space */
  points: Float32Array;
}

/**
 * Parse a LIDR binary WebSocket frame.
 *
 * Binary layout:
 * | Offset | Size | Type     | Description          |
 * |--------|------|----------|----------------------|
 * | 0      | 4    | char[4]  | Magic "LIDR"         |
 * | 4      | 4    | uint32   | Version (1)          |
 * | 8      | 8    | float64  | Unix timestamp (sec) |
 * | 16     | 4    | uint32   | Point count N        |
 * | 20     | N*12 | float32s | Points (x,y,z) * N   |
 *
 * @returns Parsed FramePayload, or null if magic bytes do not match.
 */
export function parseLidrFrame(buffer: ArrayBuffer): FramePayload | null {
  if (buffer.byteLength < 4) return null;

  const view = new DataView(buffer);
  const magic = String.fromCharCode(
    view.getUint8(0),
    view.getUint8(1),
    view.getUint8(2),
    view.getUint8(3),
  );

  if (magic !== 'LIDR') return null;

  return {
    timestamp: view.getFloat64(8, true),
    count: view.getUint32(16, true),
    points: new Float32Array(buffer.slice(20)),
  };
}

/**
 * Extract a flat-array of point arrays from a JSON WebSocket payload.
 * Matches multiple common payload shapes from the backend.
 *
 * @returns Array of [x,y,z] arrays, or null if no recognised structure found.
 */
export function parseJsonPointCloud(payload: any): any[] | null {
  if (payload == null) return null;
  if (Array.isArray(payload)) return payload;
  if (payload.points && Array.isArray(payload.points)) return payload.points;
  if (payload.data && Array.isArray(payload.data)) return payload.data;
  if (payload.data?.points && Array.isArray(payload.data.points)) return payload.data.points;
  return null;
}
