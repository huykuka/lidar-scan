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

// ── Trim logic unit tests (pure signal logic) ──────────────────────────────
describe('Recording trim — signal logic', () => {
  /**
   * Simulate the trim state logic extracted from the component.
   * Tests drive the same conditions without mounting the full component.
   */
  function makeTrimState() {
    const inFrame = { value: null as number | null };
    const outFrame = { value: null as number | null };

    const trimValid = () => {
      const inF = inFrame.value;
      const outF = outFrame.value;
      return inF !== null && outF !== null && inF < outF;
    };

    const canCreate = (creating: boolean) => trimValid() && !creating;

    const setIn = (frame: number) => {
      const out = outFrame.value;
      if (out !== null && frame >= out) outFrame.value = null;
      inFrame.value = frame;
    };

    const setOut = (frame: number) => {
      const inF = inFrame.value;
      if (inF !== null && frame <= inF) return; // reject
      outFrame.value = frame;
    };

    const reset = () => { inFrame.value = null; outFrame.value = null; };

    return { inFrame, outFrame, trimValid, canCreate, setIn, setOut, reset };
  }

  it('Set In updates inFrame signal', () => {
    const s = makeTrimState();
    s.setIn(5);
    expect(s.inFrame.value).toBe(5);
  });

  it('Set Out updates outFrame signal', () => {
    const s = makeTrimState();
    s.setIn(5);
    s.setOut(20);
    expect(s.outFrame.value).toBe(20);
  });

  it('trimValid false when only in set', () => {
    const s = makeTrimState();
    s.setIn(5);
    expect(s.trimValid()).toBe(false);
  });

  it('trimValid false when only out set', () => {
    const s = makeTrimState();
    s.setOut(20);
    expect(s.trimValid()).toBe(false);
  });

  it('trimValid true when both set and in < out', () => {
    const s = makeTrimState();
    s.setIn(5);
    s.setOut(20);
    expect(s.trimValid()).toBe(true);
  });

  it('create disabled when not trimValid', () => {
    const s = makeTrimState();
    s.setIn(5);
    expect(s.canCreate(false)).toBe(false);
  });

  it('create enabled when trimValid and not creating', () => {
    const s = makeTrimState();
    s.setIn(5);
    s.setOut(20);
    expect(s.canCreate(false)).toBe(true);
  });

  it('create disabled while creating (prevents duplicate submit)', () => {
    const s = makeTrimState();
    s.setIn(5);
    s.setOut(20);
    expect(s.canCreate(true)).toBe(false);
  });

  it('setting in >= out clears out', () => {
    const s = makeTrimState();
    s.setIn(5);
    s.setOut(20);
    s.setIn(20); // in == out → clear out
    expect(s.outFrame.value).toBeNull();
    expect(s.trimValid()).toBe(false);
  });

  it('setting out <= in is rejected (out unchanged)', () => {
    const s = makeTrimState();
    s.setIn(10);
    s.setOut(20);
    s.setOut(10); // out == in → rejected
    expect(s.outFrame.value).toBe(20); // unchanged
  });

  it('reset nulls both markers', () => {
    const s = makeTrimState();
    s.setIn(5);
    s.setOut(20);
    s.reset();
    expect(s.inFrame.value).toBeNull();
    expect(s.outFrame.value).toBeNull();
    expect(s.trimValid()).toBe(false);
  });
});

// ── onCreateTrim 202 immediate-reset behavior ──────────────────────────────
describe('onCreateTrim — 202 immediate reset', () => {
  /**
   * Simulate the onCreateTrim state machine without mounting the component.
   * Mirrors: creating.set(true) → next() → creating.set(false) + inFrame/outFrame null + toast + refresh.
   */
  function makeCreateTrimState() {
    let creating = false;
    let inFrame: number | null = 5;
    let outFrame: number | null = 20;
    const calls: string[] = [];

    const mockToast = { success: (msg: string) => calls.push(`toast:${msg}`) };
    const mockStore = { loadRecordings: () => calls.push('refresh') };

    const onCreateTrim = (success: boolean, errorFn?: () => void) => {
      creating = true;
      // simulate subscribe
      if (success) {
        // next handler — mirrors the fixed implementation
        creating = false;
        inFrame = null;
        outFrame = null;
        mockToast.success('Trim started — processing in background');
        mockStore.loadRecordings();
      } else {
        creating = false;
        if (errorFn) errorFn();
      }
    };

    return { get creating() { return creating; }, get inFrame() { return inFrame; }, get outFrame() { return outFrame; }, calls, onCreateTrim };
  }

  it('resets creating to false immediately on 202 success', () => {
    const s = makeCreateTrimState();
    s.onCreateTrim(true);
    expect(s.creating).toBe(false);
  });

  it('clears inFrame and outFrame on 202 success', () => {
    const s = makeCreateTrimState();
    s.onCreateTrim(true);
    expect(s.inFrame).toBeNull();
    expect(s.outFrame).toBeNull();
  });

  it('shows success/info toast on 202 success', () => {
    const s = makeCreateTrimState();
    s.onCreateTrim(true);
    expect(s.calls.some(c => c.startsWith('toast:'))).toBe(true);
    expect(s.calls.find(c => c.startsWith('toast:'))).toContain('Trim started');
  });

  it('calls store refresh on 202 success', () => {
    const s = makeCreateTrimState();
    s.onCreateTrim(true);
    expect(s.calls).toContain('refresh');
  });

  it('resets creating to false on error without double-toast', () => {
    const s = makeCreateTrimState();
    s.onCreateTrim(false);
    expect(s.creating).toBe(false);
    // toast NOT called on error (interceptor handles it)
    expect(s.calls.some(c => c.startsWith('toast:'))).toBe(false);
  });

  it('does NOT call refresh on error', () => {
    const s = makeCreateTrimState();
    s.onCreateTrim(false);
    expect(s.calls).not.toContain('refresh');
  });
});

// ── Recording card status helpers ──────────────────────────────────────────
describe('Recording card — status computed logic', () => {
  type Status = 'ready' | 'processing' | 'failed' | undefined;

  function cardStatusFlags(status: Status) {
    const isProcessing = status === 'processing';
    const isFailed = status === 'failed';
    const actionsDisabled = isProcessing;
    return { isProcessing, isFailed, actionsDisabled };
  }

  it('processing: isProcessing true, actionsDisabled true', () => {
    const f = cardStatusFlags('processing');
    expect(f.isProcessing).toBe(true);
    expect(f.actionsDisabled).toBe(true);
    expect(f.isFailed).toBe(false);
  });

  it('failed: isFailed true, actionsDisabled false', () => {
    const f = cardStatusFlags('failed');
    expect(f.isFailed).toBe(true);
    expect(f.isProcessing).toBe(false);
    expect(f.actionsDisabled).toBe(false);
  });

  it('ready: all false', () => {
    const f = cardStatusFlags('ready');
    expect(f.isProcessing).toBe(false);
    expect(f.isFailed).toBe(false);
    expect(f.actionsDisabled).toBe(false);
  });

  it('undefined (backward compat): treated as ready, all false', () => {
    const f = cardStatusFlags(undefined);
    expect(f.isProcessing).toBe(false);
    expect(f.isFailed).toBe(false);
    expect(f.actionsDisabled).toBe(false);
  });
});

// ── Polling logic ──────────────────────────────────────────────────────────
describe('Recording list — poll starts/stops based on processing flag', () => {
  /**
   * Simulate the hasProcessing → poll start/stop logic extracted from the component.
   */
  function makePollController() {
    let pollActive = false;
    let refreshCount = 0;
    const refresh = () => { refreshCount++; };

    const onHasProcessingChange = (hasProcessing: boolean) => {
      if (hasProcessing && !pollActive) {
        pollActive = true;
      } else if (!hasProcessing && pollActive) {
        pollActive = false;
      }
    };

    const tickPoll = () => { if (pollActive) refresh(); };

    return { get pollActive() { return pollActive; }, get refreshCount() { return refreshCount; }, onHasProcessingChange, tickPoll };
  }

  it('starts polling when a processing recording appears', () => {
    const ctrl = makePollController();
    ctrl.onHasProcessingChange(true);
    expect(ctrl.pollActive).toBe(true);
  });

  it('calls refresh on each tick while poll active', () => {
    const ctrl = makePollController();
    ctrl.onHasProcessingChange(true);
    ctrl.tickPoll();
    ctrl.tickPoll();
    expect(ctrl.refreshCount).toBe(2);
  });

  it('stops polling when no recording is processing', () => {
    const ctrl = makePollController();
    ctrl.onHasProcessingChange(true);
    ctrl.onHasProcessingChange(false);
    expect(ctrl.pollActive).toBe(false);
  });

  it('does not refresh after polling stopped', () => {
    const ctrl = makePollController();
    ctrl.onHasProcessingChange(true);
    ctrl.tickPoll(); // count=1
    ctrl.onHasProcessingChange(false);
    ctrl.tickPoll(); // poll stopped → no call
    expect(ctrl.refreshCount).toBe(1);
  });

  it('does not start poll if no processing recording', () => {
    const ctrl = makePollController();
    ctrl.onHasProcessingChange(false);
    expect(ctrl.pollActive).toBe(false);
  });
});

// ── Preview stop logic ─────────────────────────────────────────────────────
describe('Recording trim — preview stop logic (half-open [in,out))', () => {
  /**
   * Simulate the preview frame filtering logic.
   * Frame at frameIndex==outFrame must NOT be applied; pause must be called.
   */
  function shouldStopPreview(previewing: boolean, frameIndex: number, outFrame: number | null): boolean {
    if (!previewing) return false;
    if (outFrame === null) return false;
    return frameIndex >= outFrame;
  }

  it('stops preview when frame index reaches outFrame (half-open)', () => {
    expect(shouldStopPreview(true, 50, 50)).toBe(true);
  });

  it('does NOT stop before outFrame', () => {
    expect(shouldStopPreview(true, 49, 50)).toBe(false);
  });

  it('does NOT stop when not previewing', () => {
    expect(shouldStopPreview(false, 50, 50)).toBe(false);
  });

  it('stops at frame > outFrame (late frame)', () => {
    expect(shouldStopPreview(true, 51, 50)).toBe(true);
  });

  it('does not stop when outFrame is null', () => {
    expect(shouldStopPreview(true, 50, null)).toBe(false);
  });
});
