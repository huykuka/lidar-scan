import {TestBed} from '@angular/core/testing';
import {PcdParserService} from './pcd-parser.service';
import {PcdParseError} from '@core/models';

function asciiPcd(x: number, y: number, z: number, r = 255, g = 0, b = 0): ArrayBuffer {
  const header = [
    'VERSION .7',
    'FIELDS x y z r g b',
    'SIZE 4 4 4 1 1 1',
    'TYPE F F F U U U',
    'COUNT 1 1 1 1 1 1',
    'WIDTH 1',
    'HEIGHT 1',
    'VIEWPOINT 0 0 0 1 0 0 0',
    'POINTS 1',
    'DATA ascii',
    `${x} ${y} ${z} ${r} ${g} ${b}`,
  ].join('\n') + '\n';
  return new TextEncoder().encode(header).buffer;
}

function binaryPcd(points: Array<[number, number, number, number, number, number]>): ArrayBuffer {
  const header = [
    'VERSION .7',
    'FIELDS x y z r g b',
    'SIZE 4 4 4 1 1 1',
    'TYPE F F F U U U',
    'COUNT 1 1 1 1 1 1',
    `WIDTH ${points.length}`,
    'HEIGHT 1',
    'VIEWPOINT 0 0 0 1 0 0 0',
    `POINTS ${points.length}`,
    'DATA binary',
  ].join('\n') + '\n';

  const headerBytes = new TextEncoder().encode(header);
  const stride = 15;
  const dataBuffer = new ArrayBuffer(points.length * stride);
  const dv = new DataView(dataBuffer);

  points.forEach(([x, y, z, r, g, b], i) => {
    const base = i * stride;
    dv.setFloat32(base, x, true);
    dv.setFloat32(base + 4, y, true);
    dv.setFloat32(base + 8, z, true);
    dv.setUint8(base + 12, r);
    dv.setUint8(base + 13, g);
    dv.setUint8(base + 14, b);
  });

  const combined = new Uint8Array(headerBytes.byteLength + dataBuffer.byteLength);
  combined.set(new Uint8Array(headerBytes));
  combined.set(new Uint8Array(dataBuffer), headerBytes.byteLength);
  return combined.buffer;
}

describe('PcdParserService', () => {
  let service: PcdParserService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(PcdParserService);
  });

  describe('ASCII parsing', () => {
    it('should parse a single point from ASCII PCD', () => {
      const buf = asciiPcd(1.0, 2.0, 3.0, 255, 128, 0);
      const result = service.parse(buf);

      expect(result.pointCount).toBe(1);
      expect(result.positions[0]).toBeCloseTo(1.0);
      expect(result.positions[1]).toBeCloseTo(2.0);
      expect(result.positions[2]).toBeCloseTo(3.0);
      expect(result.colors[0]).toBeCloseTo(1.0);
      expect(result.colors[1]).toBeCloseTo(128 / 255);
      expect(result.colors[2]).toBeCloseTo(0.0);
    });

    it('should default to white when rgb fields missing', () => {
      const header = [
        'VERSION .7',
        'FIELDS x y z',
        'SIZE 4 4 4',
        'TYPE F F F',
        'COUNT 1 1 1',
        'WIDTH 1',
        'HEIGHT 1',
        'VIEWPOINT 0 0 0 1 0 0 0',
        'POINTS 1',
        'DATA ascii',
        '1.0 2.0 3.0',
      ].join('\n') + '\n';
      const buf = new TextEncoder().encode(header).buffer;
      const result = service.parse(buf);

      expect(result.pointCount).toBe(1);
      expect(result.colors[0]).toBe(1);
      expect(result.colors[1]).toBe(1);
      expect(result.colors[2]).toBe(1);
    });
  });

  describe('Binary parsing', () => {
    it('should parse binary PCD with two points', () => {
      const buf = binaryPcd([
        [1.0, 2.0, 3.0, 255, 0, 0],
        [4.0, 5.0, 6.0, 0, 255, 0],
      ]);
      const result = service.parse(buf);

      expect(result.pointCount).toBe(2);
      expect(result.positions[0]).toBeCloseTo(1.0);
      expect(result.positions[3]).toBeCloseTo(4.0);
      expect(result.colors[0]).toBeCloseTo(1.0);
      expect(result.colors[4]).toBeCloseTo(1.0);
    });

    it('should normalize RGB to 0-1 range', () => {
      const buf = binaryPcd([[0, 0, 0, 128, 64, 32]]);
      const result = service.parse(buf);

      expect(result.colors[0]).toBeCloseTo(128 / 255);
      expect(result.colors[1]).toBeCloseTo(64 / 255);
      expect(result.colors[2]).toBeCloseTo(32 / 255);
    });
  });

  describe('Error handling', () => {
    it('should throw PcdParseError when DATA header missing', () => {
      const malformed = new TextEncoder().encode('VERSION .7\nFIELDS x y z\n').buffer;
      expect(() => service.parse(malformed)).toThrow();
    });

    it('should throw PcdParseError on unsupported DATA type', () => {
      const header = [
        'VERSION .7',
        'FIELDS x y z',
        'SIZE 4 4 4',
        'TYPE F F F',
        'COUNT 1 1 1',
        'WIDTH 1',
        'HEIGHT 1',
        'POINTS 1',
        'DATA binary_compressed',
        '',
      ].join('\n');
      const buf = new TextEncoder().encode(header).buffer;
      expect(() => service.parse(buf)).toThrow(PcdParseError);
    });

    it('should throw PcdParseError when xyz fields missing', () => {
      const header = [
        'VERSION .7',
        'FIELDS r g b',
        'SIZE 1 1 1',
        'TYPE U U U',
        'COUNT 1 1 1',
        'WIDTH 1',
        'HEIGHT 1',
        'POINTS 1',
        'DATA ascii',
        '255 0 0',
      ].join('\n') + '\n';
      const buf = new TextEncoder().encode(header).buffer;
      expect(() => service.parse(buf)).toThrow(PcdParseError);
    });
  });
});
