import {ChangeDetectionStrategy, Component, computed, CUSTOM_ELEMENTS_SCHEMA, input,} from '@angular/core';
import * as THREE from 'three';
import {NgtArgs} from 'angular-three';
import {NgtsGrid} from 'angular-three-soba/abstractions';
import {NgtsOrthographicCamera, NgtsPerspectiveCamera} from 'angular-three-soba/cameras';
import {NgtsOrbitControls} from 'angular-three-soba/controls';
import {
  NgtsGizmoHelper,
  NgtsGizmoHelperContent,
  NgtsGizmoHelperImpl,
  NgtsGizmoViewport
} from 'angular-three-soba/gizmos';
import {ViewOrientation} from '@core/services/split-layout-store.service';
import {NgtsPoint, NgtsPointsInstances} from 'angular-three-soba/performances';

// Z-is-up coordinate system (THREE.Object3D.DEFAULT_UP = [0,0,1])
const D = 5;

const ORTHO_POS: Record<Exclude<ViewOrientation, 'perspective'>, [number, number, number]> = {
  top:    [0, 0,  D],
  bottom: [0, 0, -D],
  left:   [0, -D, 0],
  right:  [0,  D, 0],
  end:    [-D, 0, 0],
  front:  [ D, 0, 0],
};

const ORTHO_UP: Record<Exclude<ViewOrientation, 'perspective'>, [number, number, number]> = {
  top:    [0, 1, 0],
  bottom: [0, 1, 0],
  front:  [0, 0, 1],
  end:    [0, 0, 1],
  left:   [0, 0, 1],
  right:  [0, 0, 1],
};

/**
 * Shared scene-graph component: camera, orbit controls, grid, axes, gizmo.
 *
 * Usage: used directly as the `*canvasContent` child of an NgtCanvas.
 * 3D objects from the consuming component are passed via `ng-content`
 * — they are projected into this component's template which IS inside
 * the NgtCanvas embedded view, so they correctly resolve NGT_STORE.
 *
 * @example
 * <ngt-canvas style="width:100%;height:100%;display:block">
 *   <app-threed-scene-graph *canvasContent [viewType]="viewType()" [showGrid]="showGrid()">
 *     <ngts-points-buffer [positions]="buf">
 *       <ngt-points-material [size]="0.05" />
 *     </ngts-points-buffer>
 *   </app-threed-scene-graph>
 * </ngt-canvas>
 */
@Component({
  selector: 'app-threed-scene-graph',
  templateUrl: './threed-scene-graph.component.html',
  imports: [
    NgtsGrid,
    NgtsOrbitControls,
    NgtsPerspectiveCamera,
    NgtsOrthographicCamera,
    NgtsGizmoHelper,
    NgtsGizmoViewport,
    NgtArgs,
    NgtsPointsInstances,
    NgtsPoint,
    NgtsGizmoHelperImpl,
    NgtsGizmoHelperContent,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ThreedSceneGraphComponent {
  readonly viewType = input<ViewOrientation>('perspective');
  readonly showGrid = input(true);

  protected readonly Math = Math;

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
}
