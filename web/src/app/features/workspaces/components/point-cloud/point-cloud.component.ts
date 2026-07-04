import {
  ChangeDetectionStrategy,
  Component,
  computed,
  CUSTOM_ELEMENTS_SCHEMA,
  effect,
  inject,
  input,
  OnDestroy,
  viewChildren,
} from '@angular/core';

import {PointCloudDataService} from '@core/services/point-cloud-data.service';
import {ViewOrientation} from '@core/services/split-layout-store.service';
import {WorkspaceStoreService} from '@core/services/stores/workspace-store.service';
import {ShapeLayerService} from '@core/services/shape-layer.service';
import {NgtsPointsBuffer} from 'angular-three-soba/performances';
import {NgtCanvas, NgtCanvasContent, NgtCanvasImpl} from 'angular-three/dom';
import {ThreedSceneGraphComponent} from '@shared/components';

@Component({
  selector: 'app-point-cloud',
  templateUrl: './point-cloud.component.html',
  imports: [
    NgtCanvas,
    ThreedSceneGraphComponent,
    NgtsPointsBuffer,
    NgtCanvasImpl,
    NgtCanvasContent,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  providers: [ShapeLayerService],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PointCloudComponent implements OnDestroy {
  readonly viewType = input<ViewOrientation>('perspective');
  readonly viewId = input<string>('');
  readonly showGrid = input(true);

  private readonly dataService = inject(PointCloudDataService);
  private readonly workspaceStore = inject(WorkspaceStoreService);

  readonly MAX_POINTS = 250_000;
  private readonly staticBuffers = new Map<string, Float32Array>();

  protected readonly topicEntries = computed(() =>
    this.workspaceStore
      .selectedTopics()
      .filter((t) => t.enabled)
      .map((t) => {
        if (!this.staticBuffers.has(t.topic)) {
          this.staticBuffers.set(t.topic, new Float32Array(this.MAX_POINTS * 3));
        }
        return {
          topic: t.topic,
          color: t.color,
          pointSize: t.pointSize,
          buf: this.staticBuffers.get(t.topic)!,
        };
      }),
  );

  private readonly pointsBuffers = viewChildren<NgtsPointsBuffer>('buf');

  protected readonly topicFrames = computed(() =>
    this.topicEntries().map((entry) => ({
      entry,
      frame: this.dataService.frames().get(entry.topic) ?? null,
    })),
  );

  constructor() {
    effect(() => {
      const pairs = this.topicFrames();
      const bufs = this.pointsBuffers();

      pairs.forEach(({ entry, frame }, i) => {
        const points = bufs[i]?.pointsRef()?.nativeElement;
        if (!points) return;

        if (!frame || frame.count === 0) {
          points.visible = false;
          return;
        }
        points.visible = true;

        const count = Math.min(frame.count, this.MAX_POINTS);
        entry.buf.set(frame.points.subarray(0, count * 3));

        const geo = points.geometry;
        if (!geo) return;
        geo.setDrawRange(0, count);
        const attr = geo.attributes['position'];
        if (attr) attr.needsUpdate = true;
      });
    });
  }

  ngOnDestroy(): void {
    this.pointsBuffers().forEach((buf) => {
      const points = buf.pointsRef?.()?.nativeElement;
      if (!points) return;
      points.geometry?.dispose();
      const mat = points.material;
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
      else mat?.dispose();
    });
    this.staticBuffers.clear();
  }
}
