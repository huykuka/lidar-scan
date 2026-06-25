/// <reference lib="webworker" />

/**
 * Point-cloud parser Web Worker.
 *
 * Runs LIDR binary decoding and JSON→Float32Array conversion off the main
 * thread so the Angular zone / render loop is never blocked by heavy parsing.
 *
 * Message protocol
 * ────────────────
 * IN  (main → worker):
 *   { id: number, type: 'binary', topic: string, buffer: ArrayBuffer }   ← transferable
 *   { id: number, type: 'json',   topic: string, payload: string }
 *
 * OUT (worker → main):
 *   { id: number, type: 'parsed', topic: string, timestamp: number, count: number, buffer: ArrayBuffer }  ← transferable
 *   { id: number, type: 'error',  topic: string, reason: string }
 */

// ── Binary LIDR parser ────────────────────────────────────────────────────────
// Layout: magic[4] | version:u32 | timestamp:f64 | count:u32 | points:f32[N*3]
function parseBinary(buffer: ArrayBuffer): { timestamp: number; count: number; points: Float32Array } | null {
  if (buffer.byteLength < 20) return null;

  const view = new DataView(buffer);
  const magic =
    String.fromCharCode(view.getUint8(0)) +
    String.fromCharCode(view.getUint8(1)) +
    String.fromCharCode(view.getUint8(2)) +
    String.fromCharCode(view.getUint8(3));

  if (magic !== 'LIDR') return null;

  const timestamp = view.getFloat64(8, true);
  const count     = view.getUint32(16, true);

  // Copy only the points section into a fresh buffer we fully own so we
  // can transfer it back without keeping the entire WebSocket frame alive.
  const points = new Float32Array(count * 3);
  points.set(new Float32Array(buffer, 20, count * 3));

  return { timestamp, count, points };
}

// ── JSON point-cloud parser ──────────────────────────────────────────────────
function parseJson(payload: string): { count: number; points: Float32Array } | null {
  let raw: any;
  try {
    raw = JSON.parse(payload);
  } catch {
    return null;
  }

  // Accept several common backend shapes
  let arr: any[] | null = null;
  if (Array.isArray(raw))                                arr = raw;
  else if (Array.isArray(raw?.points))                   arr = raw.points;
  else if (Array.isArray(raw?.data))                     arr = raw.data;
  else if (Array.isArray(raw?.data?.points))             arr = raw.data.points;

  if (!arr || arr.length === 0) return null;

  const points = new Float32Array(arr.length * 3);
  for (let i = 0; i < arr.length; i++) {
    points[i * 3]     = arr[i][0] ?? 0;
    points[i * 3 + 1] = arr[i][1] ?? 0;
    points[i * 3 + 2] = arr[i][2] ?? 0;
  }

  return { count: arr.length, points };
}

// ── Message handler ──────────────────────────────────────────────────────────
addEventListener('message', ({ data }) => {
  const { id, type, topic } = data as { id: number; type: string; topic: string };

  try {
    if (type === 'binary') {
      const result = parseBinary(data.buffer as ArrayBuffer);
      if (!result) {
        postMessage({ id, type: 'error', topic, reason: 'invalid_magic_or_size' });
        return;
      }
      postMessage(
        { id, type: 'parsed', topic, timestamp: result.timestamp, count: result.count, buffer: result.points.buffer },
        [result.points.buffer],
      );

    } else if (type === 'json') {
      const result = parseJson(data.payload as string);
      if (!result) {
        postMessage({ id, type: 'error', topic, reason: 'unrecognised_json_shape' });
        return;
      }
      postMessage(
        { id, type: 'parsed', topic, timestamp: 0, count: result.count, buffer: result.points.buffer },
        [result.points.buffer],
      );
    }
  } catch (e) {
    postMessage({ id, type: 'error', topic, reason: String(e) });
  }
});
