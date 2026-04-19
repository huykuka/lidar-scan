import {TestBed} from '@angular/core/testing';
import {Subject} from 'rxjs';
import {vi, describe, it, expect, beforeEach, afterEach} from 'vitest';
import {ShapesWsService, MOCK_SHAPE_FRAME, SHAPES_WS_DEBOUNCE_MS} from './shapes-ws.service';
import {MultiWebsocketService} from './multi-websocket.service';
import {ShapeFrame} from '@core/models/shapes.model';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Push `count` valid frames onto `subject` with timestamps 1…count. */
function pushFrames(subject: Subject<any>, count: number): void {
  for (let i = 1; i <= count; i++) {
    const frame: ShapeFrame = {timestamp: i, shapes: []};
    subject.next(JSON.stringify(frame));
  }
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

describe('ShapesWsService', () => {
  let service: ShapesWsService;
  let mockWs: {connect: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn>};
  let wsSubject: Subject<any>;

  beforeEach(() => {
    // Use fake timers so we can control debounceTime(80) deterministically.
    vi.useFakeTimers();

    wsSubject = new Subject<any>();
    mockWs = {
      connect: vi.fn().mockReturnValue(wsSubject.asObservable()),
      disconnect: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        ShapesWsService,
        {provide: MultiWebsocketService, useValue: mockWs},
      ],
    });

    service = TestBed.inject(ShapesWsService);
  });

  afterEach(() => {
    vi.useRealTimers();
    TestBed.resetTestingModule();
  });

  // ── Sanity ──────────────────────────────────────────────────────────────

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should connect to WS topic "shapes"', () => {
    expect(mockWs.connect).toHaveBeenCalledWith('shapes', expect.any(String));
  });

  it('SHAPES_WS_DEBOUNCE_MS constant is 80', () => {
    expect(SHAPES_WS_DEBOUNCE_MS).toBe(80);
  });

  it('MOCK_SHAPE_FRAME covers all three shape types', () => {
    const types = MOCK_SHAPE_FRAME.shapes.map((s) => s.type);
    expect(types).toContain('cube');
    expect(types).toContain('plane');
    expect(types).toContain('label');
  });

  // ── Single-frame emission (debounce window must expire first) ───────────

  it('should emit ShapeFrame after debounce window when valid JSON message arrives', () => {
    const validFrame: ShapeFrame = {timestamp: 123.45, shapes: []};
    const received: ShapeFrame[] = [];

    service.frames$.subscribe((f) => received.push(f));

    wsSubject.next(JSON.stringify(validFrame));

    // Before debounce window expires: no emission yet.
    expect(received.length).toBe(0);

    // Advance past the debounce window.
    vi.advanceTimersByTime(SHAPES_WS_DEBOUNCE_MS + 1);

    expect(received.length).toBe(1);
    expect(received[0].timestamp).toBe(123.45);
    expect(received[0].shapes).toEqual([]);
  });

  // ── Error resilience ────────────────────────────────────────────────────

  it('should drop malformed JSON without crashing', () => {
    const received: ShapeFrame[] = [];
    const errors: any[] = [];
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    service.frames$.subscribe({
      next: (f) => received.push(f),
      error: (e) => errors.push(e),
    });

    wsSubject.next('NOT_VALID_JSON{{{{');
    vi.advanceTimersByTime(SHAPES_WS_DEBOUNCE_MS + 1);

    expect(received.length).toBe(0);
    expect(errors.length).toBe(0);
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });

  it('should drop message with unexpected shape (no timestamp)', () => {
    const received: ShapeFrame[] = [];
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    service.frames$.subscribe((f) => received.push(f));
    wsSubject.next(JSON.stringify({data: 'no_timestamp'}));
    vi.advanceTimersByTime(SHAPES_WS_DEBOUNCE_MS + 1);

    expect(received.length).toBe(0);
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });

  it('should complete frames$ when WS subject completes (code 1001)', () => {
    let completed = false;
    service.frames$.subscribe({complete: () => (completed = true)});

    wsSubject.complete();
    vi.advanceTimersByTime(SHAPES_WS_DEBOUNCE_MS + 1);

    expect(completed).toBe(true);
  });

  // ── Debounce / burst-coalescing ──────────────────────────────────────────
  //
  // Core acceptance-criteria test:
  //   "If 20+ frames arrive within 200 ms, only 2-3 emissions occur and each
  //    emission carries the latest frame within its debounce window."
  //
  // Timeline (SHAPES_WS_DEBOUNCE_MS = 80 ms):
  //   t=0    : push frames 1-10  → debounce timer starts
  //   t=80+1 : debounce fires → emits frame 10   (emission #1)
  //   t=100  : push frames 11-20 → new debounce timer starts
  //   t=180+1: debounce fires → emits frame 20   (emission #2)
  //   Total  : 2 emissions for 20 frames in ≤ 200 ms ✓

  it('should coalesce 20+ frames within 200 ms to ≤ 3 emissions (latest frame per window)', () => {
    const received: ShapeFrame[] = [];
    service.frames$.subscribe((f) => received.push(f));

    // Burst 1 at t=0: frames 1–10
    pushFrames(wsSubject, 10);

    // Debounce window has NOT expired yet.
    expect(received.length).toBe(0);

    // Expire window → should emit only frame #10 (latest in burst).
    vi.advanceTimersByTime(SHAPES_WS_DEBOUNCE_MS + 1);
    expect(received.length).toBe(1);
    expect(received[0].timestamp).toBe(10);

    // Burst 2 at t≈100: frames 11–20
    pushFrames(wsSubject, 10); // timestamps restart at 1..10, but we only care about count

    // Emit burst 2 with actual timestamps for verification.
    for (let i = 11; i <= 20; i++) {
      wsSubject.next(JSON.stringify({timestamp: i, shapes: []} as ShapeFrame));
    }

    expect(received.length).toBe(1); // still only 1 — window not yet expired

    // Expire second window → emits frame 20.
    vi.advanceTimersByTime(SHAPES_WS_DEBOUNCE_MS + 1);
    expect(received.length).toBe(2);
    expect(received[1].timestamp).toBe(20);

    // Total: 2 emissions for 20 (actually 30) frames — well within 2-3 ✓
    expect(received.length).toBeGreaterThanOrEqual(1);
    expect(received.length).toBeLessThanOrEqual(3);
  });

  it('should emit the LATEST frame in each debounce window (not the first)', () => {
    const received: ShapeFrame[] = [];
    service.frames$.subscribe((f) => received.push(f));

    // Three frames rapid-fired — only timestamp=300 must survive.
    wsSubject.next(JSON.stringify({timestamp: 100, shapes: []} as ShapeFrame));
    wsSubject.next(JSON.stringify({timestamp: 200, shapes: []} as ShapeFrame));
    wsSubject.next(JSON.stringify({timestamp: 300, shapes: []} as ShapeFrame));

    vi.advanceTimersByTime(SHAPES_WS_DEBOUNCE_MS + 1);

    expect(received.length).toBe(1);
    expect(received[0].timestamp).toBe(300);
  });

  it('debounce is reset by each incoming frame within the window', () => {
    const received: ShapeFrame[] = [];
    service.frames$.subscribe((f) => received.push(f));

    // Send frames at t=0, t=50, t=100 — each < 80 ms after the previous,
    // so the debounce timer keeps resetting.
    wsSubject.next(JSON.stringify({timestamp: 1, shapes: []} as ShapeFrame));
    vi.advanceTimersByTime(50); // t=50 — still within window
    expect(received.length).toBe(0);

    wsSubject.next(JSON.stringify({timestamp: 2, shapes: []} as ShapeFrame));
    vi.advanceTimersByTime(50); // t=100 — still within window (timer reset at t=50)
    expect(received.length).toBe(0);

    wsSubject.next(JSON.stringify({timestamp: 3, shapes: []} as ShapeFrame));
    vi.advanceTimersByTime(SHAPES_WS_DEBOUNCE_MS + 1); // t=181 — window expires

    expect(received.length).toBe(1);
    expect(received[0].timestamp).toBe(3);
  });
});
