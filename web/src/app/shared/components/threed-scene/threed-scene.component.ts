import {ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, input,} from '@angular/core';
import {NgtCanvasContent, NgtCanvasImpl} from 'angular-three/dom';
import {ThreedSceneGraphComponent} from '@shared/components';
import {ViewOrientation} from '@core/services/split-layout-store.service';

/**
 * Convenience wrapper: NgtCanvas + ThreedSceneGraphComponent.
 *
 * Use this when you have NO additional 3D objects to add to the scene.
 * If you need to project 3D objects into the scene, use NgtCanvas directly
 * with `<app-threed-scene-graph *canvasContent>` and put your objects inside it.
 */
@Component({
  selector: 'app-threed-scene',
  template: `
    <ngt-canvas style="width:100%;height:100%;display:block">
      <app-threed-scene-graph
        *canvasContent
        [viewType]="viewType()"
        [showGrid]="showGrid()"
      />
    </ngt-canvas>
  `,
  styleUrl: './threed-scene.component.css',
  imports: [ThreedSceneGraphComponent, NgtCanvasImpl, NgtCanvasContent],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ThreedSceneComponent {
  readonly viewType = input<ViewOrientation>('perspective');
  readonly showGrid = input(true);
}
