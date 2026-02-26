// pcd-decoder.worker.ts
// Decodes PCD files (both ASCII and binary formats) in a Web Worker

self.onmessage = async (event) => {
  const { action, payload } = event.data;

  switch (action) {
    case 'decode': {
      const { buffer, frameIndex } = payload;
      const result = parsePCD(buffer);
      self.postMessage({ action: 'decoded', payload: { result, frameIndex } });
      break;
    }
  }
};

/**
 * Parse PCD file (binary or ASCII) and extract point cloud data.
 * Binary format is 10x faster than ASCII.
 */
function parsePCD(
  buffer: Uint8Array,
): { points: Float32Array; intensities: Float32Array; count: number } | null {
  const textDecoder = new TextDecoder('ascii');
  
  // Read enough bytes to parse the header
  const headerBytes = buffer.slice(0, Math.min(1000, buffer.length));
  const headerText = textDecoder.decode(headerBytes);
  
  // Detect format (binary or ASCII)
  const isBinary = headerText.includes('DATA binary');
  const isAscii = headerText.includes('DATA ascii');
  
  if (!isBinary && !isAscii) {
    console.error('PCD: Invalid format - no DATA section found');
    return null;
  }
  
  // Parse header to get metadata
  const lines = headerText.split('\n');
  let pointsCount = 0;
  let dims = 3;
  
  for (const line of lines) {
    if (line.startsWith('POINTS')) {
      pointsCount = parseInt(line.split(/\s+/)[1], 10);
    } else if (line.startsWith('FIELDS')) {
      dims = line.split(/\s+/).length - 1;
    }
  }
  
  if (pointsCount === 0) {
    console.error('PCD: No points found in header');
    return null;
  }
  
  if (isBinary) {
    return parseBinaryPCD(buffer, headerText, pointsCount, dims);
  } else {
    return parseAsciiPCD(buffer, headerText, pointsCount, dims);
  }
}

/**
 * Parse binary PCD format (10x faster, 3-4x smaller)
 */
function parseBinaryPCD(
  buffer: Uint8Array,
  headerText: string,
  pointsCount: number,
  dims: number
): { points: Float32Array; intensities: Float32Array; count: number } | null {
  // Find the start of binary data (after "DATA binary\n")
  const dataKeyword = 'DATA binary';
  const dataIndex = headerText.indexOf(dataKeyword);
  
  if (dataIndex === -1) {
    console.error('PCD: DATA binary not found');
    return null;
  }
  
  // Find newline after "DATA binary"
  let binaryStartOffset = 0;
  for (let i = dataIndex; i < buffer.length; i++) {
    if (buffer[i] === 10) { // '\n'
      binaryStartOffset = i + 1;
      break;
    }
  }
  
  // Binary data: pointsCount * dims * 4 bytes (float32)
  const expectedBytes = pointsCount * dims * 4;
  const binaryData = buffer.slice(binaryStartOffset, binaryStartOffset + expectedBytes);
  
  if (binaryData.length < expectedBytes) {
    console.error(`PCD: Insufficient binary data. Expected ${expectedBytes}, got ${binaryData.length}`);
    return null;
  }
  
  // Create Float32Array view of the binary data
  const allFields = new Float32Array(binaryData.buffer, binaryData.byteOffset, pointsCount * dims);
  
  // Extract x, y, z (first 3 fields) and intensity (field 13 for SICK/Pipeline)
  const outPoints = new Float32Array(pointsCount * 3);
  const outIntensities = new Float32Array(pointsCount);
  let validCount = 0;
  
  for (let i = 0; i < pointsCount; i++) {
    const offset = i * dims;
    const x = allFields[offset];
    const y = allFields[offset + 1];
    const z = allFields[offset + 2];
    
    // Intensity is typically at index 13 for 16-field SICK data, or index 13 for 14-field pipeline
    const intensity = dims > 13 ? allFields[offset + 13] : 0;
    
    // Filter out zero points (optional - comment out if you want to keep them)
    if (x !== 0 || y !== 0 || z !== 0) {
      outPoints[validCount * 3] = x;
      outPoints[validCount * 3 + 1] = y;
      outPoints[validCount * 3 + 2] = z;
      outIntensities[validCount] = intensity;
      validCount++;
    }
  }
  
  return {
    points: outPoints.slice(0, validCount * 3),
    intensities: outIntensities.slice(0, validCount),
    count: validCount,
  };
}

/**
 * Parse ASCII PCD format (legacy - slow for large point clouds)
 */
function parseAsciiPCD(
  buffer: Uint8Array,
  headerText: string,
  pointsCount: number,
  dims: number
): { points: Float32Array; intensities: Float32Array; count: number } | null {
  const textDecoder = new TextDecoder('ascii');
  const fullText = textDecoder.decode(buffer);
  
  const asciiHeaderStr = 'DATA ascii';
  const asciiIndex = fullText.indexOf(asciiHeaderStr);
  
  if (asciiIndex === -1) {
    console.error('PCD: DATA ascii header not found');
    return null;
  }
  
  const dataIndex = fullText.indexOf('\n', asciiIndex) + 1;
  const dataPart = fullText.substring(dataIndex);
  const dataLines = dataPart.split('\n');
  
  const outPoints = new Float32Array(pointsCount * 3);
  const outIntensities = new Float32Array(pointsCount);
  let validCount = 0;
  
  for (const line of dataLines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    
    const parts = trimmed.split(/\s+/);
    if (parts.length < 3) continue;
    
    const x = parseFloat(parts[0]);
    const y = parseFloat(parts[1]);
    const z = parseFloat(parts[2]);
    // Intensity is usually at index 13 in SICK/Pipeline data (16 or 14 cols)
    const intensity = parts.length > 13 ? parseFloat(parts[13]) : 0;
    
    // Filter out zero points (optional)
    if (x !== 0 || y !== 0 || z !== 0) {
      if (validCount < pointsCount) {
        outPoints[validCount * 3] = x;
        outPoints[validCount * 3 + 1] = y;
        outPoints[validCount * 3 + 2] = z;
        outIntensities[validCount] = intensity;
        validCount++;
      }
    }
  }
  
  return {
    points: outPoints.slice(0, validCount * 3),
    intensities: outIntensities.slice(0, validCount),
    count: validCount,
  };
}
