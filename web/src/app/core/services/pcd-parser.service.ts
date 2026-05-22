import {Injectable} from '@angular/core';
import {PcdParseError, PcdParseResult} from '@core/models';

/**
 * PcdParserService
 *
 * Parses PCD 0.7 ASCII and binary formats.
 * Binary format assumes: little-endian, fields x y z r g b (float32 + uint8).
 * Point stride: 4+4+4+1+1+1 = 15 bytes per point.
 */
@Injectable({
  providedIn: 'root',
})
export class PcdParserService {
  /**
   * Parse a PCD file from an ArrayBuffer.
   * Supports both ASCII and binary DATA sections.
   */
  parse(buffer: ArrayBuffer): PcdParseResult {
    const bytes = new Uint8Array(buffer);

    // Find end of ASCII header (line ending with "DATA ascii\n" or "DATA binary\n")
    const {headerEnd, header} = this.parseHeader(bytes);

    const fields = header['FIELDS']?.split(/\s+/) ?? [];
    const types = header['TYPE']?.split(/\s+/) ?? [];
    const sizes = header['SIZE']?.split(/\s+/).map(Number) ?? [];
    const dataType = header['DATA']?.trim().toLowerCase();
    const pointCount = parseInt(header['WIDTH'] ?? header['POINTS'] ?? '0', 10);

    if (!fields.length || !dataType) {
      throw new PcdParseError('Invalid PCD header: missing FIELDS or DATA');
    }

    const xIdx = fields.indexOf('x');
    const yIdx = fields.indexOf('y');
    const zIdx = fields.indexOf('z');
    const rIdx = fields.indexOf('r');
    const gIdx = fields.indexOf('g');
    const bIdx = fields.indexOf('b');

    if (xIdx === -1 || yIdx === -1 || zIdx === -1) {
      throw new PcdParseError('PCD missing required x, y, z fields');
    }

    if (dataType === 'ascii') {
      return this.parseAscii(bytes, headerEnd, xIdx, yIdx, zIdx, rIdx, gIdx, bIdx, pointCount);
    } else if (dataType === 'binary') {
      return this.parseBinary(
        buffer,
        headerEnd,
        fields,
        types,
        sizes,
        xIdx,
        yIdx,
        zIdx,
        rIdx,
        gIdx,
        bIdx,
        pointCount,
      );
    } else {
      throw new PcdParseError(`Unsupported PCD DATA type: ${dataType}`);
    }
  }

  private parseHeader(bytes: Uint8Array): {headerEnd: number; header: Record<string, string>} {
    const decoder = new TextDecoder('ascii');
    const header: Record<string, string> = {};
    let headerEnd = 0;
    let offset = 0;

    while (offset < bytes.length) {
      const lineStart = offset;
      // Find end of line
      while (offset < bytes.length && bytes[offset] !== 0x0a) {
        offset++;
      }
      const line = decoder.decode(bytes.subarray(lineStart, offset)).trim();
      offset++; // skip \n

      const spaceIdx = line.indexOf(' ');
      if (spaceIdx !== -1) {
        const key = line.substring(0, spaceIdx).toUpperCase();
        const value = line.substring(spaceIdx + 1);
        header[key] = value;

        if (key === 'DATA') {
          headerEnd = offset;
          break;
        }
      }
    }

    if (!header['DATA']) {
      throw new PcdParseError('PCD header does not contain DATA field');
    }

    return {headerEnd, header};
  }

  private parseAscii(
    bytes: Uint8Array,
    headerEnd: number,
    xIdx: number,
    yIdx: number,
    zIdx: number,
    rIdx: number,
    gIdx: number,
    bIdx: number,
    estimatedCount: number,
  ): PcdParseResult {
    const decoder = new TextDecoder('ascii');
    const text = decoder.decode(bytes.subarray(headerEnd));
    const lines = text.trim().split('\n');

    const count = estimatedCount > 0 ? estimatedCount : lines.length;
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    let actualCount = 0;

    for (let i = 0; i < lines.length && actualCount < count; i++) {
      const parts = lines[i].trim().split(/\s+/);
      if (parts.length === 0 || parts[0] === '') continue;

      const x = parseFloat(parts[xIdx]);
      const y = parseFloat(parts[yIdx]);
      const z = parseFloat(parts[zIdx]);

      if (isNaN(x) || isNaN(y) || isNaN(z)) continue;

      positions[actualCount * 3] = x;
      positions[actualCount * 3 + 1] = y;
      positions[actualCount * 3 + 2] = z;

      if (rIdx !== -1 && gIdx !== -1 && bIdx !== -1) {
        colors[actualCount * 3] = parseFloat(parts[rIdx]) / 255;
        colors[actualCount * 3 + 1] = parseFloat(parts[gIdx]) / 255;
        colors[actualCount * 3 + 2] = parseFloat(parts[bIdx]) / 255;
      } else {
        // default white
        colors[actualCount * 3] = 1;
        colors[actualCount * 3 + 1] = 1;
        colors[actualCount * 3 + 2] = 1;
      }

      actualCount++;
    }

    return {
      positions: positions.subarray(0, actualCount * 3) as Float32Array,
      colors: colors.subarray(0, actualCount * 3) as Float32Array,
      pointCount: actualCount,
    };
  }

  private parseBinary(
    buffer: ArrayBuffer,
    headerEnd: number,
    fields: string[],
    types: string[],
    sizes: number[],
    xIdx: number,
    yIdx: number,
    zIdx: number,
    rIdx: number,
    gIdx: number,
    bIdx: number,
    pointCount: number,
  ): PcdParseResult {
    // Calculate stride: sum of all field sizes
    const stride = sizes.reduce((sum, s) => sum + s, 0);
    if (stride === 0) {
      throw new PcdParseError('Cannot compute binary stride: SIZE fields invalid');
    }

    // Compute field byte offsets
    const offsets: number[] = [];
    let off = 0;
    for (const s of sizes) {
      offsets.push(off);
      off += s;
    }

    const dataView = new DataView(buffer, headerEnd);
    const availableBytes = buffer.byteLength - headerEnd;
    const actualCount = Math.min(pointCount, Math.floor(availableBytes / stride));

    if (actualCount === 0) {
      throw new PcdParseError('Binary PCD: no points found in data section');
    }

    const positions = new Float32Array(actualCount * 3);
    const colors = new Float32Array(actualCount * 3);

    for (let i = 0; i < actualCount; i++) {
      const base = i * stride;
      positions[i * 3] = dataView.getFloat32(base + offsets[xIdx], true);
      positions[i * 3 + 1] = dataView.getFloat32(base + offsets[yIdx], true);
      positions[i * 3 + 2] = dataView.getFloat32(base + offsets[zIdx], true);

      if (rIdx !== -1 && gIdx !== -1 && bIdx !== -1) {
        // Type U = uint8
        colors[i * 3] = dataView.getUint8(base + offsets[rIdx]) / 255;
        colors[i * 3 + 1] = dataView.getUint8(base + offsets[gIdx]) / 255;
        colors[i * 3 + 2] = dataView.getUint8(base + offsets[bIdx]) / 255;
      } else {
        colors[i * 3] = 1;
        colors[i * 3 + 1] = 1;
        colors[i * 3 + 2] = 1;
      }
    }

    return {positions, colors, pointCount: actualCount};
  }
}
