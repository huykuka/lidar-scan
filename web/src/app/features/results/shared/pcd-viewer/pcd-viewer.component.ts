import {
  ChangeDetectionStrategy,
  Component,
  computed,
  CUSTOM_ELEMENTS_SCHEMA,
  effect,
  inject,
  input,
  OnDestroy,
  signal,
  viewChild,
} from '@angular/core';
import * as THREE from 'three';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {PcdParserService} from '@core/services/pcd-parser.service';
import {NgtsPointsBuffer} from 'angular-three-soba/performances';
import {NgtCanvas, NgtCanvasContent, NgtCanvasImpl} from 'angular-three/dom';
import {ThreedSceneGraphComponent, ViewportOverlayComponent} from '@shared/components';
import {ViewOrientation} from '@core/services/split-layout-store.service';

const MAX_POINTS = 500_000;
const POINT_SIZE = 0.04;

@Component({
  selector: 'app-pcd-viewer',
  imports: [SynergyComponentsModule, NgtCanvas, ThreedSceneGraphComponent, NgtsPointsBuffer, NgtCanvasImpl, NgtCanvasContent, ViewportOverlayComponent],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './pcd-viewer.component.html',
  styleUrl: './pcd-viewer.component.css',
})
export class PcdViewerComponent implements OnDestroy {
  readonly pcdUrl = input<string>('');
  readonly color = input<string>('');

  /** Optional download callback — when provided, a download button is shown over the canvas. */
  readonly onDownload = input<(() => void) | null>(null);

  protected readonly isLoading = signal(false);
  protected readonly hasError = signal(false);
  protected readonly errorMessage = signal('');
  protected readonly showGrid = signal(true);
  protected readonly viewOrientation = signal<ViewOrientation>('perspective');

  /** Pre-allocated position buffer, mutated in-place on each load. */
  protected readonly positionsBuffer = new Float32Array(MAX_POINTS * 3);
  /** Pre-allocated color buffer, mutated in-place on each load. */
  protected readonly colorsBuffer = new Float32Array(MAX_POINTS * 3);
  /** How many points are valid in the current frame. */
  protected readonly pointCount = signal(0);

  protected readonly pointSize = POINT_SIZE;

  /** When a color override is set, use it; otherwise rely on vertex colors from the PCD. */
  protected readonly useVertexColors = computed(() => !this.color());
  protected readonly materialColor = computed(() => this.color() || '#ffffff');

  private readonly pointsBufRef = viewChild<NgtsPointsBuffer>('pointsBuf');
  private readonly parser = inject(PcdParserService);

  constructor() {
    // React to pcdUrl changes
    effect(() => {
      const url = this.pcdUrl();
      if (url) {
        this.loadPcd(url);
      } else {
        this.pointCount.set(0);
      }
    });

    // When color override changes, force material update via pointCount signal re-flush
    effect(() => {
      this.color(); // track
      this.flushGeometry();
    });
  }

  ngOnDestroy(): void {
    const buf = this.pointsBufRef();
    const points = buf?.pointsRef?.()?.nativeElement;
    if (points) {
      points.geometry?.dispose();
      const mat = points.material;
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
      else (mat as THREE.Material)?.dispose();
    }
  }

  private async loadPcd(url: string): Promise<void> {
    this.isLoading.set(true);
    this.hasError.set(false);

    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const buffer = await response.arrayBuffer();
      const result = this.parser.parse(buffer);

      if (result.pointCount > MAX_POINTS) {
        console.warn(
          `[PcdViewer] Point count ${result.pointCount} exceeds cap ${MAX_POINTS}; truncating.`,
        );
      }

      const count = Math.min(result.pointCount, MAX_POINTS);
      this.positionsBuffer.set(result.positions.subarray(0, count * 3));
      this.colorsBuffer.set(result.colors.subarray(0, count * 3));
      this.pointCount.set(count);
      this.flushGeometry();
    } catch (err) {
      console.error('[PcdViewer] Failed to load or parse PCD:', err);
      this.hasError.set(true);
      this.errorMessage.set('Unable to render point cloud');
    } finally {
      this.isLoading.set(false);
    }
  }

  private flushGeometry(): void {
    const buf = this.pointsBufRef();
    const points = buf?.pointsRef?.()?.nativeElement;
    if (!points) return;
    const count = this.pointCount();
    const geo = points.geometry;
    if (!geo) return;
    geo.setDrawRange(0, count);
    const posAttr = geo.attributes['position'];
    const colAttr = geo.attributes['color'];
    if (posAttr) posAttr.needsUpdate = true;
    if (colAttr) colAttr.needsUpdate = true;
  }
}
