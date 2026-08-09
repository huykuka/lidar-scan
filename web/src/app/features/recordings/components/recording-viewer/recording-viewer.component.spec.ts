import {copyStreamedXyz, fitPointCloudToView, flushPointCloudGeometry, readyAction} from './recording-viewer-stream-state';

describe('RecordingViewerComponent stream startup', () => {
  it('starts only once per stream session', () => {
    expect(readyAction(2, 1, -1)).toBe('start');
    expect(readyAction(2, 1, 1)).toBe('ignore');
    expect(readyAction(2, 2, 1)).toBe('start');
  });

  it('does not start empty recording', () => {
    expect(readyAction(0, 1, -1)).toBe('eof');
    expect(readyAction(0, 1, 1)).toBe('eof');
  });

  it('flushes streamed XYZ count into rendered geometry', () => {
    const position = {needsUpdate: false};
    const geometry = {
      attributes: {position},
      setDrawRange: vi.fn(),
    };
    const points = {visible: false, geometry};

    // XYZ payload already copied into bounded positionsBuffer by component.
    flushPointCloudGeometry(points, 2);

    expect(points.visible).toBe(true);
    expect(geometry.setDrawRange).toHaveBeenCalledWith(0, 2);
    expect(position.needsUpdate).toBe(true);
  });

  it('copies valid streamed XYZ into bounded buffer and makes render target ready', () => {
    const position = {needsUpdate: false};
    const geometry = {attributes: {position}, setDrawRange: vi.fn()};
    const points = {visible: false, geometry};
    const destination = new Float32Array(9);

    const count = copyStreamedXyz(points, destination, new Float32Array([1, 2, 3, 4, 5, 6]), 2, 3);

    expect(count).toBe(2);
    expect(destination[0]).toBeLessThan(0);
    expect(destination[3]).toBeGreaterThan(0);
    expect(points.visible).toBe(true);
    expect(geometry.setDrawRange).toHaveBeenCalledWith(0, 2);
    expect(position.needsUpdate).toBe(true);
  });

  it('fits large world coordinates into camera view without extra frame storage', () => {
    const points = new Float32Array([1000, 2000, 3000, 1004, 2000, 3000]);

    fitPointCloudToView(points, 2);

    expect([...points]).toEqual([-4, 0, 0, 4, 0, 0]);
  });

  it('keeps empty streamed frames hidden with zero draw range', () => {
    const geometry = {attributes: {}, setDrawRange: vi.fn()};
    const points = {visible: true, geometry};

    flushPointCloudGeometry(points, 0);

    expect(points.visible).toBe(false);
    expect(geometry.setDrawRange).toHaveBeenCalledWith(0, 0);
  });
});
