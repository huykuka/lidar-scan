import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  OnDestroy,
  computed,
  effect,
  inject,
  input,
  viewChildren,
} from '@angular/core';
import * as THREE from 'three';

import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { PointCloudDataService } from '@core/services/point-cloud-data.service';
import { ViewOrientation } from '@core/services/split-layout-store.service';
import { WorkspaceStoreService } from '@core/services/stores/workspace-store.service';
import { ShapeLayerService } from '@core/services/shape-layer.service';
import { NgtsGrid } from 'angular-three-soba/abstractions';
import { NgtCanvas } from 'angular-three/dom';
import { NgtsOrbitControls } from 'angular-three-soba/controls';
import { NgtsPerspectiveCamera, NgtsOrthographicCamera } from 'angular-three-soba/cameras';
import { NgtsGizmoHelper, NgtsGizmoViewport } from 'angular-three-soba/gizmos';
import { NgtsPointsBuffer, NgtsPointsInstances, NgtsPoint } from 'angular-three-soba/performances';
import { NgtArgs } from 'angular-three';

// Z-is-up coordinate system (THREE.Object3D.DEFAULT_UP = [0,0,1])
const D = 5;

// Camera positions per view — Z is up, Y is forward/backward
const ORTHO_POS: Record<Exclude<ViewOrientation, 'perspective'>, [number, number, number]> = {
  top: [0, 0, D], // looking down  (-Z)
  bottom: [0, 0, -D], // looking up    (+Z)
  left: [0, -D, 0], // looking +Y (front face)
  right: [0, D, 0], // looking -Y (back face)
  end: [-D, 0, 0], // looking +X
  front: [D, 0, 0], // looking -X
};

// Camera up-vectors per view (Z-up world)
const ORTHO_UP: Record<Exclude<ViewOrientation, 'perspective'>, [number, number, number]> = {
  top:    [0, 1, 0],   // Y = screen up when looking down
  bottom: [0, 1, 0],   // Y = screen up when looking up
  front:  [0, 0, 1],   // Z = screen up when looking along Y
  end:    [0, 0, 1],
  left:   [0, 0, 1],
  right:  [0, 0, 1],
};

@Component({
  selector: 'app-point-cloud',
  templateUrl: './point-cloud.component.html',
  imports: [
    SynergyComponentsModule,
    NgtCanvas,
    NgtsGrid,
    NgtsOrbitControls,
    NgtsPerspectiveCamera,
    NgtsOrthographicCamera,
    NgtsGizmoHelper,
    NgtsGizmoViewport,
    NgtsPointsBuffer,
    NgtArgs,
    NgtsPointsInstances,
    NgtsPoint,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  providers: [ShapeLayerService],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PointCloudComponent implements OnDestroy {
  readonly viewType = input<ViewOrientation>('perspective');
  readonly viewId = input<string>('');
  readonly showGrid = input(true);

  // Perspective: position behind and above in Z-up space
  protected readonly perspCameraOptions = {
    makeDefault: true,
    position: [-15, 15, 10] as [number, number, number],
    fov: 50,
    near: 0.1,
    far: 1000,
  };

  protected readonly orthoCameraOptions = computed(() => {
    const vt = this.viewType() as Exclude<ViewOrientation, 'perspective'>;
    return {
      makeDefault: true,
      zoom: 20,
      near: 0.1,
      far: 1000,
      position: ORTHO_POS[vt],
      up: ORTHO_UP[vt],
    };
  });

  protected readonly orbitOptions = computed(() => ({
    makeDefault: true,
    enableDamping: true,
    enableRotate: this.viewType() === 'perspective',
  }));

  protected readonly gizmoOptions = { margin: [80, 80] as [number, number] };
  protected readonly Math = Math;

  protected readonly gridOptions = computed(() => ({
    cellSize: 1,
    sectionSize: 5,
    cellThickness: 0.5,
    sectionThickness: 1.3,
    cellColor: '#797676',
    infiniteGrid: false,
    fadeDistance: 9_999,
    fadeStrength: 1.5,
    side: THREE.DoubleSide,
    planeArgs: [30, 30] as [number, number],
  }));

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
