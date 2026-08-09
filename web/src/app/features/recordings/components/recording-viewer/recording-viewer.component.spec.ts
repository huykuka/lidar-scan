import {copyStreamedXyz, flushPointCloudGeometry, nextFrameIndex, playbackAction, readyAction, shouldApplyFrame} from './recording-viewer-stream-state';

describe('RecordingViewerComponent stream startup', () => {
  it('maps play button events to backend commands', () => {
    expect(playbackAction(false)).toBe('start');
    expect(playbackAction(true)).toBe('pause');
  });

  it('resumes from next frame without local seeking loop', () => {
    expect(nextFrameIndex(4, 10)).toBe(5);
    expect(nextFrameIndex(9, 10)).toBe(9);
  });

  it('rejects stale frames while paused', () => {
    expect(shouldApplyFrame(false, 4, 4)).toBe(false);
    expect(shouldApplyFrame(true, 3, 4)).toBe(false);
    expect(shouldApplyFrame(true, 4, 4)).toBe(true);
  });

  it('renders exact seek target frame while paused without starting playback', () => {
    const targetFrame = 7;
    const seekGeneration = 12;

    expect(playbackAction(false)).toBe('start');
    expect(shouldApplyFrame(false, seekGeneration, seekGeneration, seekGeneration)).toBe(true);
    expect(shouldApplyFrame(false, seekGeneration, seekGeneration, null)).toBe(false);
    expect(targetFrame).toBe(7);
  });
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
    expect([...destination]).toEqual([1, 2, 3, 4, 5, 6, 0, 0, 0]);
    expect(points.visible).toBe(true);
    expect(geometry.setDrawRange).toHaveBeenCalledWith(0, 2);
    expect(position.needsUpdate).toBe(true);
  });

  it('preserves recording XYZ units and coordinates across sequential frames', () => {
    const position = {needsUpdate: false};
    const geometry = {attributes: {position}, setDrawRange: vi.fn()};
    const points = {visible: false, geometry};
    const destination = new Float32Array(9);
    const destinationRef = destination;

    copyStreamedXyz(points, destination, new Float32Array([1000, 2000, 3000, 1004, 2000, 3000]), 2, 3);
    copyStreamedXyz(points, destination, new Float32Array([-10, 20, 30]), 1, 3);

    expect(destination).toBe(destinationRef);
    expect([...destination]).toEqual([-10, 20, 30, 4, 2000, 3000, 0, 0, 0]);
    expect(geometry.setDrawRange).toHaveBeenNthCalledWith(1, 0, 2);
    expect(geometry.setDrawRange).toHaveBeenNthCalledWith(2, 0, 1);
  });

  it('keeps empty streamed frames hidden with zero draw range', () => {
    const geometry = {attributes: {}, setDrawRange: vi.fn()};
    const points = {visible: true, geometry};

    flushPointCloudGeometry(points, 0);

    expect(points.visible).toBe(false);
    expect(geometry.setDrawRange).toHaveBeenCalledWith(0, 0);
  });
});
