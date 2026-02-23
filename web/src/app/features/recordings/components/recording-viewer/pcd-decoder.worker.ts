// pcd-decoder.worker.ts

self.onmessage = async (event) => {
  const { action, payload } = event.data;

  switch (action) {
    case 'decode': {
      const { text, frameIndex } = payload;
      const result = parsePCD(text);
      self.postMessage({ action: 'decoded', payload: { result, frameIndex } });
      break;
    }
  }
};

function parsePCD(text: string): { points: Float32Array; count: number } | null {
  const lines = text.split('\n');
  let pointCount = 0;
  let dataStart = 0;

  // Parse header
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('POINTS')) {
      pointCount = parseInt(line.split(' ')[1]);
    }
    if (line.startsWith('DATA')) {
      dataStart = i + 1;
      break;
    }
  }

  if (pointCount === 0) return null;

  // Parse points and filter out zeros (no lidar return)
  const tempPoints: number[] = [];

  for (let i = dataStart; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    const values = line.split(/\s+/).map((v) => parseFloat(v));
    if (values.length >= 3) {
      const x = values[0];
      const y = values[1];
      const z = values[2];

      // Skip points at origin (0, 0, 0) - these are invalid lidar returns
      if (x !== 0 || y !== 0 || z !== 0) {
        tempPoints.push(x, y, z);
      }
    }
  }

  // Convert to Float32Array
  const points = new Float32Array(tempPoints);
  const validCount = tempPoints.length / 3;
  return { points, count: validCount };
}