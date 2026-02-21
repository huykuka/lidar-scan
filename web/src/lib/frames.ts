const HEADER_BYTES = 20
const MAGIC = 'LIDR'

export interface LidarFrame {
  version: number
  timestamp: number
  count: number
  points: Float32Array
}

const textDecoder = new TextDecoder('ascii')

export function parseLidrFrame(buffer: ArrayBuffer): LidarFrame {
  if (buffer.byteLength < HEADER_BYTES) {
    throw new Error('Frame too small')
  }

  const view = new DataView(buffer)
  const magic = textDecoder.decode(buffer.slice(0, 4))

  if (magic !== MAGIC) {
    throw new Error(`Unexpected magic ${magic}`)
  }

  const version = view.getUint32(4, true)
  const timestamp = view.getFloat64(8, true)
  const count = view.getUint32(16, true)
  const expectedBytes = HEADER_BYTES + count * 12

  if (buffer.byteLength < expectedBytes) {
    throw new Error('Frame payload truncated')
  }

  const points = new Float32Array(buffer, HEADER_BYTES, count * 3).slice()
  return { version, timestamp, count, points }
}

export function formatFrameSummary(frame: Pick<LidarFrame, 'count' | 'timestamp'>) {
  const time = new Date(frame.timestamp * 1000)
  const timeLabel = Number.isFinite(time.getTime()) ? time.toLocaleTimeString() : 'n/a'
  return `${frame.count.toLocaleString()} pts @ ${timeLabel}`
}
