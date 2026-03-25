import { parseLidrFrame, parseJsonPointCloud } from './lidr-parser';

describe('parseLidrFrame', () => {
  function buildLidrBuffer(count: number, timestamp = 1234567890.5): ArrayBuffer {
    // Header: 4 magic + 4 version + 8 timestamp + 4 count = 20 bytes
    const headerSize = 20;
    const pointData = count * 3 * 4; // N * 3 floats * 4 bytes
    const buf = new ArrayBuffer(headerSize + pointData);
    const view = new DataView(buf);

    // Magic: 'LIDR'
    view.setUint8(0, 76); // 'L'
    view.setUint8(1, 73); // 'I'
    view.setUint8(2, 68); // 'D'
    view.setUint8(3, 82); // 'R'

    // Version: 1
    view.setUint32(4, 1, true);

    // Timestamp
    view.setFloat64(8, timestamp, true);

    // Count
    view.setUint32(16, count, true);

    // Points: fill with predictable values (i*0.1 for xyz)
    const points = new Float32Array(buf, headerSize);
    for (let i = 0; i < count * 3; i++) {
      points[i] = i * 0.1;
    }

    return buf;
  }

  it('should return null when magic bytes do not match', () => {
    const buf = new ArrayBuffer(20);
    const view = new DataView(buf);
    view.setUint8(0, 65); // 'A'
    view.setUint8(1, 66); // 'B'
    view.setUint8(2, 67); // 'C'
    view.setUint8(3, 68); // 'D'
    expect(parseLidrFrame(buf)).toBeNull();
  });

  it('should return null for an empty buffer', () => {
    expect(parseLidrFrame(new ArrayBuffer(0))).toBeNull();
  });

  it('should parse the timestamp correctly from a valid LIDR frame', () => {
    const ts = 9876543210.123;
    const buf = buildLidrBuffer(10, ts);
    const result = parseLidrFrame(buf);
    expect(result).not.toBeNull();
    expect(result!.timestamp).toBeCloseTo(ts, 2);
  });

  it('should parse the point count correctly', () => {
    const count = 42;
    const buf = buildLidrBuffer(count);
    const result = parseLidrFrame(buf)!;
    expect(result.count).toBe(count);
  });

  it('should return a Float32Array of the correct length (count * 3)', () => {
    const count = 100;
    const buf = buildLidrBuffer(count);
    const result = parseLidrFrame(buf)!;
    expect(result.points).toBeInstanceOf(Float32Array);
    expect(result.points.length).toBe(count * 3);
  });

  it('should correctly decode point values', () => {
    const count = 3;
    const buf = buildLidrBuffer(count);
    const result = parseLidrFrame(buf)!;
    expect(result.points[0]).toBeCloseTo(0, 5);
    expect(result.points[1]).toBeCloseTo(0.1, 5);
    expect(result.points[2]).toBeCloseTo(0.2, 5);
  });

  it('should handle zero-point frame (count = 0)', () => {
    const buf = buildLidrBuffer(0);
    const result = parseLidrFrame(buf)!;
    expect(result.count).toBe(0);
    expect(result.points.length).toBe(0);
  });
});

describe('parseJsonPointCloud', () => {
  it('should return null for null payload', () => {
    expect(parseJsonPointCloud(null)).toBeNull();
  });

  it('should return null for undefined payload', () => {
    expect(parseJsonPointCloud(undefined)).toBeNull();
  });

  it('should return the array itself if payload is a plain array', () => {
    const input = [[1, 2, 3], [4, 5, 6]];
    expect(parseJsonPointCloud(input)).toBe(input);
  });

  it('should return payload.points if it is an array', () => {
    const pts = [[1, 2, 3]];
    expect(parseJsonPointCloud({ points: pts })).toBe(pts);
  });

  it('should return payload.data if it is an array', () => {
    const data = [[7, 8, 9]];
    expect(parseJsonPointCloud({ data })).toBe(data);
  });

  it('should return payload.data.points if it is an array', () => {
    const pts = [[0, 0, 1]];
    expect(parseJsonPointCloud({ data: { points: pts } })).toBe(pts);
  });

  it('should return null if no recognized structure found', () => {
    expect(parseJsonPointCloud({ foo: 'bar' })).toBeNull();
  });
});
