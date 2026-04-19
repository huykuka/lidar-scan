import {Injectable, inject} from '@angular/core';
import {Observable, of, Subject} from 'rxjs';
import {debounceTime, delay, repeat} from 'rxjs/operators';
import {MultiWebsocketService} from './multi-websocket.service';
import {ShapeFrame, ShapeDescriptor} from '@core/models/shapes.model';
import {environment} from '@env/environment';

/**
 * Debounce window (ms) applied to the **live** WebSocket stream.
 * Coalesces rapid bursts of shape frames so that only the latest frame
 * within each window is forwarded to subscribers, preventing visual flicker.
 *
 * Mock mode is intentionally excluded — it emits a steady 100 ms tick
 * for FE-02 local-development tests and must not be throttled.
 */
export const SHAPES_WS_DEBOUNCE_MS = 80;

// ── Mock frame (FE-02) — covers all three shape types ─────────────────────────
//
// NOTE: The cube already embeds its own label sprite (built by ShapeBuilders.buildCube
// when `label` is non-null).  A redundant standalone LabelDescriptor for the same
// text at nearly the same position caused visible duplication.  Only add a standalone
// label shape when it refers to a *different* annotation that has no parent geometry.
export const MOCK_SHAPE_FRAME: ShapeFrame = {
  timestamp: 1713523800.341,
  shapes: [
    {
      id: 'a3f9c21b88d41e02',
      node_name: 'Cluster Detector',
      type: 'cube',
      center: [1.2, 0.5, 0.3],
      size: [0.8, 0.6, 1.2],
      rotation: [0.0, 0.0, 0.0],
      color: '#00ff00',
      opacity: 0.4,
      wireframe: true,
      // Label is embedded by ShapeBuilders.buildCube — no separate LabelDescriptor needed.
      label: 'Person (conf: 0.91)',
    } as ShapeDescriptor,
    {
      id: 'b7e41ca099f33d10',
      node_name: 'Ground Segmenter',
      type: 'plane',
      center: [0.0, 0.0, -0.05],
      normal: [0.0, 0.0, 1.0],
      width: 20.0,
      height: 20.0,
      color: '#4488ff',
      opacity: 0.2,
    } as ShapeDescriptor,
    // Standalone label example — distinct from the cube label above,
    // positioned at a separate annotation point in the scene.
    {
      id: 'c1f08bb452aa71e9',
      node_name: 'Scene Info',
      type: 'label',
      position: [-2.0, 0.0, 1.0],
      text: 'Origin reference',
      font_size: 14,
      color: '#ffff00',
      background_color: '#00000099',
      scale: 1.0,
    } as ShapeDescriptor,
  ],
};

const WS_TOPIC = 'shapes';

/**
 * Subscribes to the 'shapes' WebSocket topic and emits decoded ShapeFrame
 * objects. Handles JSON parsing with error resilience and mock-mode for
 * local development without a backend.
 */
@Injectable({providedIn: 'root'})
export class ShapesWsService {
  private readonly wsService = inject(MultiWebsocketService);

  /**
   * Stream of decoded ShapeFrame objects from the 'shapes' WS topic.
   * In mock mode (environment.mockShapes), emits the MOCK_SHAPE_FRAME every
   * 100 ms instead of connecting to the backend.
   */
  readonly frames$: Observable<ShapeFrame>;

  constructor() {
    if ((environment as any).mockShapes) {
      this.frames$ = of(MOCK_SHAPE_FRAME).pipe(delay(0), repeat({delay: 100}));
      return;
    }

    const subject = new Subject<ShapeFrame>();

    // We reuse the MultiWebsocketService which already implements the 1001
    // close-code logic (completes on 1001, reconnects on other codes).
    const url = environment.wsUrl(WS_TOPIC);
    const raw$ = this.wsService.connect(WS_TOPIC, url);

    raw$.subscribe({
      next: (data: any) => {
        try {
          const raw = typeof data === 'string' ? JSON.parse(data) : data;
          if (raw && typeof raw.timestamp === 'number' && Array.isArray(raw.shapes)) {
            subject.next(raw as ShapeFrame);
          } else {
            console.error('[ShapesWsService] Unexpected message shape — dropping frame:', raw);
          }
        } catch (err) {
          console.error('[ShapesWsService] JSON parse error — dropping frame:', err);
        }
      },
      complete: () => subject.complete(),
      error: (err) => subject.error(err),
    });

    // Debounce coalesces rapid bursts: only the latest frame within each
    // SHAPES_WS_DEBOUNCE_MS window is emitted.  This prevents visual flicker
    // during high-frequency sensor updates without dropping the final state.
    this.frames$ = subject.asObservable().pipe(debounceTime(SHAPES_WS_DEBOUNCE_MS));
  }
}
