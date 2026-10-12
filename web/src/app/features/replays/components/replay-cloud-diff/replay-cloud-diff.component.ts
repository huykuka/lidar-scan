import {
  ChangeDetectionStrategy,
  Component,
  computed,
  CUSTOM_ELEMENTS_SCHEMA,
  DestroyRef,
  effect,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import {takeUntilDestroyed, toObservable} from '@angular/core/rxjs-interop';
import {catchError, combineLatest, debounceTime, of, switchMap, tap} from 'rxjs';
import {NgtsPointsBuffer} from 'angular-three-soba/performances';
import {NgtCanvas, NgtCanvasContent, NgtCanvasImpl} from 'angular-three/dom';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {ThreedSceneGraphComponent, ViewportOverlayComponent} from '@shared/components';
import {ViewOrientation} from '@core/services/split-layout-store.service';
import {ReplayApiService} from '@core/services/api/replay-api.service';
import {CloudNode} from '@core/models';
import {flushPointCloudGeometry} from '../../../recordings/components/recording-viewer/recording-viewer-stream-state';
import {CloudDiff, DiffLayers, parseCloudDiff, splitDiffLayers} from '../../utils/cloud-diff-parser';

/** Capacity of each layer buffer (points). Matches the recording viewer. */
const MAX_POINTS = 250_000;
const DEFAULT_TOLERANCE = 0.05;
const REQUEST_DEBOUNCE_MS = 120;

export const LAYER_COLORS = {matched: '#94a3b8', onlyA: '#ef4444', onlyB: '#3b82f6'} as const;

@Component({
  selector: 'app-replay-cloud-diff',
  imports: [
    SynergyComponentsModule,
    NgtCanvas,
    NgtCanvasContent,
    NgtCanvasImpl,
    NgtsPointsBuffer,
    ThreedSceneGraphComponent,
    ViewportOverlayComponent,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './replay-cloud-diff.component.html',
  styleUrl: './replay-cloud-diff.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReplayCloudDiffComponent {
  readonly runA = input.required<string>();
  readonly runB = input.required<string>();
  readonly nodes = input.required<CloudNode[]>();
  /** Recording frame to jump to (e.g. when a chart is clicked). */
  readonly requestedFrame = input<number | null>(null);

  private readonly api = inject(ReplayApiService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly colors = LAYER_COLORS;

  // ── Selection ────────────────────────────────────────────────────────────
  protected readonly nodeId = signal<string>('');
  /** Index into the selected node's (common) frame list. */
  protected readonly frameIndex = signal(0);
  protected readonly tolerance = signal(DEFAULT_TOLERANCE);

  protected readonly node = computed(() => this.nodes().find((n) => n.node_id === this.nodeId()));
  protected readonly frames = computed(() => this.node()?.frames ?? []);
  protected readonly frame = computed<number | null>(() => this.frames()[this.frameIndex()] ?? null);

  // ── Display ──────────────────────────────────────────────────────────────
  protected readonly showMatched = signal(true);
  protected readonly showOnlyA = signal(true);
  protected readonly showOnlyB = signal(true);
  protected readonly pointSize = signal(0.15);
  protected readonly showGrid = signal(true);
  protected readonly viewOrientation = signal<ViewOrientation>('perspective');

  // ── Result ───────────────────────────────────────────────────────────────
  protected readonly isLoading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly stats = signal<CloudDiff | null>(null);
  protected readonly layers = signal<DiffLayers>({matched: 0, onlyA: 0, onlyB: 0});

  protected readonly matchedBuffer = new Float32Array(MAX_POINTS * 3);
  protected readonly onlyABuffer = new Float32Array(MAX_POINTS * 3);
  protected readonly onlyBBuffer = new Float32Array(MAX_POINTS * 3);

  private readonly matchedRef = viewChild<NgtsPointsBuffer>('matchedPts');
  private readonly onlyARef = viewChild<NgtsPointsBuffer>('onlyAPts');
  private readonly onlyBRef = viewChild<NgtsPointsBuffer>('onlyBPts');

  constructor() {
    // Keep the selected node valid when the list of comparable nodes changes.
    effect(() => {
      const list = this.nodes();
      if (!list.some((n) => n.node_id === this.nodeId())) {
        this.nodeId.set(list[0]?.node_id ?? '');
        this.frameIndex.set(0);
      }
    });

    // Jump to a requested recording frame (nearest available one).
    effect(() => {
      const wanted = this.requestedFrame();
      const frames = this.frames();
      if (wanted === null || frames.length === 0) return;
      let best = 0;
      frames.forEach((f, i) => {
        if (Math.abs(f - wanted) < Math.abs(frames[best] - wanted)) best = i;
      });
      this.frameIndex.set(best);
    });

    // Fetch on node / frame / tolerance change; switchMap drops stale responses while scrubbing.
    combineLatest([
      toObservable(this.runA),
      toObservable(this.runB),
      toObservable(this.nodeId),
      toObservable(this.frame),
      toObservable(this.tolerance),
    ])
      .pipe(
        debounceTime(REQUEST_DEBOUNCE_MS),
        tap(() => this.isLoading.set(true)),
        switchMap(([a, b, nodeId, frame, tol]) => {
          if (!nodeId || frame === null) return of(null);
          return this.api.getCloudDiff(a, b, nodeId, frame, tol).pipe(
            catchError((err) => {
              this.error.set(err?.error?.detail ?? 'Could not load this frame.');
              return of(null);
            }),
          );
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((buffer) => {
        this.isLoading.set(false);
        if (!buffer) return;
        try {
          const diff = parseCloudDiff(buffer);
          this.layers.set(splitDiffLayers(diff, this.matchedBuffer, this.onlyABuffer, this.onlyBBuffer));
          this.stats.set(diff);
          this.error.set(null);
        } catch (e) {
          this.error.set(e instanceof Error ? e.message : 'Invalid point cloud data');
        }
      });

    // Push layer counts (respecting the visibility toggles) into the Three.js geometries.
    this.bindLayer(this.matchedRef, () => (this.showMatched() ? this.layers().matched : 0));
    this.bindLayer(this.onlyARef, () => (this.showOnlyA() ? this.layers().onlyA : 0));
    this.bindLayer(this.onlyBRef, () => (this.showOnlyB() ? this.layers().onlyB : 0));
  }

  private bindLayer(ref: () => NgtsPointsBuffer | undefined, count: () => number): void {
    effect(() => {
      const points = ref()?.pointsRef()?.nativeElement;
      const n = count();
      if (!points) return;
      flushPointCloudGeometry(points, n);
    });
  }

  // ── Handlers ─────────────────────────────────────────────────────────────
  protected selectNode(id: string): void {
    this.nodeId.set(id);
    this.frameIndex.set(0);
  }

  protected setFrameIndex(value: string | number): void {
    const i = Math.round(Number(value));
    if (Number.isFinite(i)) this.frameIndex.set(Math.min(Math.max(i, 0), Math.max(this.frames().length - 1, 0)));
  }

  protected step(delta: number): void {
    this.setFrameIndex(this.frameIndex() + delta);
  }

  protected setTolerance(value: string): void {
    const t = Number(value);
    if (Number.isFinite(t) && t > 0) this.tolerance.set(Math.min(t, 10));
  }

  protected fmt(value: number | undefined, digits = 4): string {
    return value === undefined ? '—' : value.toPrecision(digits);
  }
}
