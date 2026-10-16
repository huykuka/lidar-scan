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
import {NgtsPointsBuffer} from 'angular-three-soba/performances';
import {NgtCanvas, NgtCanvasContent} from 'angular-three/dom';
import {catchError, combineLatest, debounceTime, of, switchMap, tap} from 'rxjs';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {ThreedSceneGraphComponent, ViewportOverlayComponent} from '@shared/components';
import {ViewOrientation} from '@core/services/split-layout-store.service';
import {ReplayApiService} from '@core/services/api/replay-api.service';
import {flushPointCloudGeometry} from '../../../recordings/components/recording-viewer/recording-viewer-stream-state';

/** Capacity of the buffer (points); matches the capture cap per frame. */
const MAX_POINTS = 250_000;
const REQUEST_DEBOUNCE_MS = 120;

export interface FrameCloudNode {
  id: string;
  name: string;
}

/** 3D view of one node's captured point cloud at one frame of a single run. */
@Component({
  selector: 'app-replay-frame-cloud',
  imports: [SynergyComponentsModule, NgtCanvas, NgtCanvasContent, NgtsPointsBuffer, ThreedSceneGraphComponent, ViewportOverlayComponent],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './replay-frame-cloud.component.html',
  styleUrl: './replay-frame-cloud.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReplayFrameCloudComponent {
  readonly runId = input.required<string>();
  /** Nodes whose clouds were captured for this run. */
  readonly nodes = input.required<FrameCloudNode[]>();
  readonly frame = input.required<number>();

  private readonly api = inject(ReplayApiService);
  private readonly destroyRef = inject(DestroyRef);

  private readonly selectedId = signal('');
  protected readonly nodeId = computed(() => {
    const list = this.nodes();
    return list.some((n) => n.id === this.selectedId()) ? this.selectedId() : (list[0]?.id ?? '');
  });

  protected readonly pointSize = signal(0.15);
  protected readonly showGrid = signal(true);
  protected readonly viewOrientation = signal<ViewOrientation>('perspective');

  protected readonly isLoading = signal(false);
  /** Set when the chosen frame has no stored cloud (frames can be skipped by capture). */
  protected readonly missing = signal(false);
  protected readonly count = signal(0);

  protected readonly buffer = new Float32Array(MAX_POINTS * 3);
  private readonly pointsRef = viewChild<NgtsPointsBuffer>('pts');

  constructor() {
    combineLatest([toObservable(this.runId), toObservable(this.nodeId), toObservable(this.frame)])
      .pipe(
        debounceTime(REQUEST_DEBOUNCE_MS),
        tap(() => this.isLoading.set(true)),
        switchMap(([run, node, frame]) => {
          if (!node) return of(null);
          return this.api.getRunCloud(run, node, frame).pipe(catchError(() => of(null)));
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((data) => {
        this.isLoading.set(false);
        if (!data || data.byteLength < 12) {
          this.missing.set(true);
          this.count.set(0);
          return;
        }
        const xyz = new Float32Array(data, 0, Math.floor(data.byteLength / 12) * 3);
        const n = Math.min(xyz.length / 3, MAX_POINTS);
        this.buffer.set(xyz.subarray(0, n * 3));
        this.missing.set(false);
        this.count.set(n);
      });

    effect(() => {
      const points = this.pointsRef()?.pointsRef()?.nativeElement;
      const n = this.count();
      if (points) flushPointCloudGeometry(points, n);
    });
  }

  protected selectNode(id: string): void {
    this.selectedId.set(id);
  }
}
