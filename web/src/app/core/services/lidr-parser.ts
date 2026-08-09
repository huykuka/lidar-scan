export interface FramePayload {
  timestamp: number;
  count: number;
  points: Float32Array;
}

export interface LidrFrame {
  type: 'frame';
  generation: number;
  frameIndex: number;
  timestamp: number;
  pointCount: number;
  xyz: Float32Array;
}

export interface LidrFrameError {
  type: 'error';
  code: 'invalid_frame';
  message: string;
}

export type LidrParseResult = LidrFrame | LidrFrameError;

export function parseLidrFrame(buffer: ArrayBuffer): LidrParseResult {
  const invalid = (message: string): LidrFrameError => ({type: 'error', code: 'invalid_frame', message});
  if (buffer.byteLength < 28) return invalid('Frame header is incomplete');

  const view = new DataView(buffer);
  const magic = String.fromCharCode(...new Uint8Array(buffer, 0, 4));
  if (magic !== 'LIDR') return invalid('Invalid LIDR magic');
  if (view.getUint32(4, true) !== 2) return invalid('Unsupported LIDR version');

  const pointCount = view.getUint32(24, true);
  const expectedLength = 28 + pointCount * 3 * 4;
  if (buffer.byteLength !== expectedLength) return invalid('Frame payload length does not match point count');

  return {
    type: 'frame',
    generation: view.getUint32(8, true),
    frameIndex: view.getUint32(12, true),
    timestamp: view.getFloat64(16, true),
    pointCount,
    xyz: new Float32Array(buffer, 28, pointCount * 3),
  };
}

export function parseJsonPointCloud(payload: any): any[] | null {
  if (payload === null || payload === undefined) return null;
  if (Array.isArray(payload)) return payload;
  if (payload.points && Array.isArray(payload.points)) return payload.points;
  if (payload.data && Array.isArray(payload.data)) return payload.data;
  if (payload.data?.points && Array.isArray(payload.data.points)) return payload.data.points;
  return null;
}
