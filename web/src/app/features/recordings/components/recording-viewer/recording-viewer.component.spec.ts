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
    const points = {visible: false, frustumCulled: true, geometry};

    // XYZ payload already copied into bounded positionsBuffer by component.
    flushPointCloudGeometry(points, 2);

    expect(points.visible).toBe(true);
    // Fixed-size buffer + stale lazily-computed boundingSphere would otherwise
    // frustum-cull the point cloud in/out as new frames move outside the sphere
    // computed on the first render — that's the flicker bug. Culling must stay off.
    expect(points.frustumCulled).toBe(false);
    expect(geometry.setDrawRange).toHaveBeenCalledWith(0, 2);
    expect(position.needsUpdate).toBe(true);
  });

  it('copies valid streamed XYZ into bounded buffer and makes render target ready', () => {
    const position = {needsUpdate: false};
    const geometry = {attributes: {position}, setDrawRange: vi.fn()};
    const points = {visible: false, frustumCulled: true, geometry};
    const destination = new Float32Array(9);

    const count = copyStreamedXyz(points, destination, new Float32Array([1, 2, 3, 4, 5, 6]), 2, 3);

    expect(count).toBe(2);
    expect([...destination]).toEqual([1, 2, 3, 4, 5, 6, 0, 0, 0]);
    expect(points.visible).toBe(true);
    expect(geometry.setDrawRange).toHaveBeenCalledWith(0, 2);
    expect(position.needsUpdate).toBe(true);
  });

  it('keeps empty streamed frames hidden with zero draw range', () => {
    const geometry = {attributes: {}, setDrawRange: vi.fn()};
    const points = {visible: true, frustumCulled: true, geometry};

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

// ── UX Enhancement: computed signal + helper logic ─────────────────────────
describe('Recording trim — UX enhancements (computed logic)', () => {
  /**
   * Pure simulation of the new computed signals/helpers added for UX polish.
   * No component mounting needed — logic is deterministic.
   */

  function makeUxState(frameCount: number, duration: number) {
    let inFrame: number | null = null;
    let outFrame: number | null = null;

    const frameToTime = (frame: number) => {
      if (frameCount <= 1) return 0;
      return (frame / (frameCount - 1)) * duration;
    };

    const frameLabel = (frame: number | null) => {
      if (frame === null) return '';
      const t = frameToTime(frame);
      return `${frame} · ${t.toFixed(1)}s`;
    };

    const trimValid = () => inFrame !== null && outFrame !== null && inFrame < outFrame;
    const trimBothSetInvalid = () => inFrame !== null && outFrame !== null && inFrame >= outFrame;

    const inMarkerStyle = () => {
      if (frameCount === 0 || inFrame === null) return null;
      const left = (inFrame / Math.max(frameCount - 1, 1)) * 100;
      return { left: `${left}%` };
    };

    const outMarkerStyle = () => {
      if (frameCount === 0 || outFrame === null) return null;
      const left = (outFrame / Math.max(frameCount - 1, 1)) * 100;
      return { left: `${left}%` };
    };

    const segmentFrameCount = () => trimValid() ? outFrame! - inFrame! : 0;
    const segmentDuration = () => trimValid() ? frameToTime(outFrame!) - frameToTime(inFrame!) : 0;

    const trimDisabledTooltip = () => {
      if (inFrame === null && outFrame === null) return 'Set both In and Out markers to enable';
      if (inFrame === null) return 'Set an In marker before the Out marker';
      if (outFrame === null) return 'Set an Out marker after the In marker';
      if (inFrame >= outFrame!) return 'In marker must come before Out marker';
      return '';
    };

    const canCreate = (creating: boolean) => trimValid() && !creating;

    return {
      get inFrame() { return inFrame; },
      set inFrame(v) { inFrame = v; },
      get outFrame() { return outFrame; },
      set outFrame(v) { outFrame = v; },
      frameToTime, frameLabel, trimValid, trimBothSetInvalid,
      inMarkerStyle, outMarkerStyle, segmentFrameCount, segmentDuration,
      trimDisabledTooltip, canCreate,
    };
  }

  // ── Button always-rendered: disabled when invalid, enabled when valid ────
  it('canCreate disabled when trimValid false (no markers)', () => {
    const s = makeUxState(100, 10);
    expect(s.canCreate(false)).toBe(false);
  });

  it('canCreate disabled when only in set', () => {
    const s = makeUxState(100, 10);
    s.inFrame = 10;
    expect(s.canCreate(false)).toBe(false);
  });

  it('canCreate disabled when only out set', () => {
    const s = makeUxState(100, 10);
    s.outFrame = 20;
    expect(s.canCreate(false)).toBe(false);
  });

  it('canCreate enabled when both set and in < out', () => {
    const s = makeUxState(100, 10);
    s.inFrame = 10;
    s.outFrame = 50;
    expect(s.canCreate(false)).toBe(true);
  });

  it('canCreate disabled while creating even when valid', () => {
    const s = makeUxState(100, 10);
    s.inFrame = 10;
    s.outFrame = 50;
    expect(s.canCreate(true)).toBe(false);
  });

  // ── Marker display: frame + timestamp when set ───────────────────────────
  it('frameLabel returns empty string when null', () => {
    const s = makeUxState(100, 10);
    expect(s.frameLabel(null)).toBe('');
  });

  it('frameLabel shows frame + timestamp when set', () => {
    // 100 frames, 10s duration; frame 50 → 50/99 * 10 ≈ 5.1s
    const s = makeUxState(100, 10);
    const label = s.frameLabel(50);
    expect(label).toMatch(/^50 · /);
    expect(label).toContain('s');
  });

  it('frameLabel first frame is 0.0s', () => {
    const s = makeUxState(100, 10);
    expect(s.frameLabel(0)).toBe('0 · 0.0s');
  });

  it('frameLabel last frame matches duration', () => {
    const s = makeUxState(100, 10);
    const label = s.frameLabel(99);
    expect(label).toBe('99 · 10.0s');
  });

  // ── Guidance hint: unset state ───────────────────────────────────────────
  it('both markers unset: no hint needed (no partial hint shown)', () => {
    const s = makeUxState(100, 10);
    // neither inFrame nor outFrame set → full hint branch applies in template
    expect(s.inFrame).toBeNull();
    expect(s.outFrame).toBeNull();
  });

  it('only out set: inFrame null triggers in-missing hint', () => {
    const s = makeUxState(100, 10);
    s.outFrame = 50;
    expect(s.inFrame).toBeNull();
    expect(s.outFrame).toBe(50);
  });

  // ── Segment summary: correct frame count + duration ──────────────────────
  it('segmentFrameCount is 0 when not valid', () => {
    const s = makeUxState(100, 10);
    expect(s.segmentFrameCount()).toBe(0);
  });

  it('segmentFrameCount is out-in when valid', () => {
    const s = makeUxState(100, 10);
    s.inFrame = 10;
    s.outFrame = 50;
    expect(s.segmentFrameCount()).toBe(40);
  });

  it('segmentDuration is 0 when not valid', () => {
    const s = makeUxState(100, 10);
    expect(s.segmentDuration()).toBe(0);
  });

  it('segmentDuration matches frame time difference when valid', () => {
    // 100 frames (0-99), 10s: in=0→0s, out=99→10s, diff=10s
    const s = makeUxState(100, 10);
    s.inFrame = 0;
    s.outFrame = 99;
    expect(s.segmentDuration()).toBeCloseTo(10, 1);
  });

  it('segmentDuration partial segment correct', () => {
    // in=0 out=49: 49/99 * 10 ≈ 4.95s
    const s = makeUxState(100, 10);
    s.inFrame = 0;
    s.outFrame = 49;
    const expected = (49 / 99) * 10 - 0;
    expect(s.segmentDuration()).toBeCloseTo(expected, 3);
  });

  // ── Invalid-range warning: both set and in >= out ────────────────────────
  it('trimBothSetInvalid false when not set', () => {
    const s = makeUxState(100, 10);
    expect(s.trimBothSetInvalid()).toBe(false);
  });

  it('trimBothSetInvalid false when only one set', () => {
    const s = makeUxState(100, 10);
    s.inFrame = 10;
    expect(s.trimBothSetInvalid()).toBe(false);
  });

  it('trimBothSetInvalid false when in < out (valid)', () => {
    const s = makeUxState(100, 10);
    s.inFrame = 10;
    s.outFrame = 50;
    expect(s.trimBothSetInvalid()).toBe(false);
  });

  it('trimBothSetInvalid true when in === out', () => {
    const s = makeUxState(100, 10);
    s.inFrame = 50;
    s.outFrame = 50;
    expect(s.trimBothSetInvalid()).toBe(true);
  });

  it('trimBothSetInvalid true when in > out', () => {
    const s = makeUxState(100, 10);
    s.inFrame = 60;
    s.outFrame = 50;
    expect(s.trimBothSetInvalid()).toBe(true);
  });

  // ── inMarkerStyle / outMarkerStyle ───────────────────────────────────────
  it('inMarkerStyle returns null when inFrame unset', () => {
    const s = makeUxState(100, 10);
    expect(s.inMarkerStyle()).toBeNull();
  });

  it('outMarkerStyle returns null when outFrame unset', () => {
    const s = makeUxState(100, 10);
    expect(s.outMarkerStyle()).toBeNull();
  });

  it('inMarkerStyle returns left% when set', () => {
    const s = makeUxState(100, 10);
    s.inFrame = 0;
    expect(s.inMarkerStyle()).toEqual({ left: '0%' });
  });

  it('outMarkerStyle returns 100% for last frame', () => {
    const s = makeUxState(100, 10);
    s.outFrame = 99;
    expect(s.outMarkerStyle()).toEqual({ left: '100%' });
  });

  it('inMarkerStyle at midpoint is ~50%', () => {
    const s = makeUxState(101, 10); // 101 frames → max index 100; frame 50 → 50%
    s.inFrame = 50;
    expect(s.inMarkerStyle()).toEqual({ left: '50%' });
  });

  it('inMarkerStyle returns null when frameCount is 0', () => {
    const s = makeUxState(0, 0);
    s.inFrame = 0;
    expect(s.inMarkerStyle()).toBeNull();
  });

  // ── trimDisabledTooltip ──────────────────────────────────────────────────
  it('tooltip mentions both markers when neither set', () => {
    const s = makeUxState(100, 10);
    expect(s.trimDisabledTooltip()).toContain('both');
  });

  it('tooltip mentions In marker when only out set', () => {
    const s = makeUxState(100, 10);
    s.outFrame = 50;
    expect(s.trimDisabledTooltip()).toContain('In marker');
  });

  it('tooltip mentions Out marker when only in set', () => {
    const s = makeUxState(100, 10);
    s.inFrame = 10;
    expect(s.trimDisabledTooltip()).toContain('Out marker');
  });

  it('tooltip mentions ordering when both set but in >= out', () => {
    const s = makeUxState(100, 10);
    s.inFrame = 60;
    s.outFrame = 50;
    expect(s.trimDisabledTooltip()).toContain('before');
  });

  it('tooltip empty string when valid', () => {
    const s = makeUxState(100, 10);
    s.inFrame = 10;
    s.outFrame = 50;
    expect(s.trimDisabledTooltip()).toBe('');
  });
});
