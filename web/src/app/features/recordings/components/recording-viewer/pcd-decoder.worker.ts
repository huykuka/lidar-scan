// pcd-decoder.worker.ts

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

function parsePCD(
  buffer: Uint8Array,
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
  const header = fullText.substring(0, dataIndex);
  const lines = header.split('\n');

  let pointsCount = 0;
  let dims = 3;

  for (const line of lines) {
    if (line.startsWith('POINTS')) {
      pointsCount = parseInt(line.split(/\s+/)[1], 10);
    } else if (line.startsWith('FIELDS')) {
      dims = line.split(/\s+/).length - 1;
    }
  }

  if (pointsCount === 0) return null;

  let outPoints = new Float32Array(pointsCount * 3);
  let outIntensities = new Float32Array(pointsCount);
  let validCount = 0;

  const dataPart = fullText.substring(dataIndex);
  const dataLines = dataPart.split('\n');

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
