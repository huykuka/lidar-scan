import {TestBed} from '@angular/core/testing';
import {Subject} from 'rxjs';
import {vi, describe, it, expect, beforeEach} from 'vitest';
import {ShapesWsService, MOCK_SHAPE_FRAME} from './shapes-ws.service';
import {MultiWebsocketService} from './multi-websocket.service';
import {ShapeFrame} from '@core/models/shapes.model';

describe('ShapesWsService', () => {
  let service: ShapesWsService;
  let mockWs: {connect: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn>};
  let wsSubject: Subject<any>;

  beforeEach(() => {
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

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should connect to WS topic "shapes"', () => {
    expect(mockWs.connect).toHaveBeenCalledWith('shapes', expect.any(String));
  });

  it('should emit ShapeFrame when valid JSON message arrives', () => {
    const validFrame: ShapeFrame = {timestamp: 123.45, shapes: []};
    const received: ShapeFrame[] = [];

    service.frames$.subscribe((f) => received.push(f));

    wsSubject.next(JSON.stringify(validFrame));

    expect(received.length).toBe(1);
    expect(received[0].timestamp).toBe(123.45);
    expect(received[0].shapes).toEqual([]);
  });

  it('should drop malformed JSON without crashing', () => {
    const received: ShapeFrame[] = [];
    const errors: any[] = [];
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    service.frames$.subscribe({
      next: (f) => received.push(f),
      error: (e) => errors.push(e),
    });

    wsSubject.next('NOT_VALID_JSON{{{{');

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

    expect(received.length).toBe(0);
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });

  it('should complete frames$ when WS subject completes (code 1001)', () => {
    let completed = false;
    service.frames$.subscribe({complete: () => (completed = true)});

    wsSubject.complete();

    expect(completed).toBe(true);
  });

  it('MOCK_SHAPE_FRAME covers all three shape types', () => {
    const types = MOCK_SHAPE_FRAME.shapes.map((s) => s.type);
    expect(types).toContain('cube');
    expect(types).toContain('plane');
    expect(types).toContain('label');
  });
});
