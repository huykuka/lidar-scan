import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
} from '@angular/core';
import {
  SplitLayoutStoreService,
  ViewPane,
} from '@core/services/split-layout-store.service';
import {PointCloudDataService} from '@core/services/point-cloud-data.service';
import {ViewportOverlayComponent as SharedViewportOverlayComponent} from '@shared/components';
import {ViewOrientation} from '@core/services/split-layout-store.service';

/**
 * Workspace-specific viewport overlay adapter.
 * Bridges the workspace's ViewPane model to the shared generic overlay component.
 */
@Component({
  selector: 'app-viewport-overlay',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SharedViewportOverlayComponent],
  template: `
    <app-shared-viewport-overlay
      [orientation]="pane().orientation"
      [showGrid]="showGridState()"
      [hasData]="hasData()"
      (orientationChange)="onOrientationChange($event)"
      (gridToggle)="onGridToggle($event)"
    />
  `,
})
export class ViewportOverlayComponent {
  readonly pane = input.required<ViewPane>();
  readonly gridToggled = output<boolean>();

  private layout = inject(SplitLayoutStoreService);
  private dataService = inject(PointCloudDataService);

  protected showGridState = computed(() => true);
  protected hasData = computed(() => this.dataService.frames().size > 0);

  onOrientationChange(value: ViewOrientation): void {
    this.layout.setPaneOrientation(this.pane().id, value);
  }

  onGridToggle(value: boolean): void {
    this.gridToggled.emit(value);
  }
}
