import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
} from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { SplitLayoutStoreService, ViewPane, ViewOrientation } from '@core/services/split-layout-store.service';
import { PointCloudDataService } from '@core/services/point-cloud-data.service';

interface OrientationOption {
  value: ViewOrientation;
  label: string;
}

@Component({
  selector: 'app-viewport-overlay',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SynergyComponentsModule],
  templateUrl: './viewport-overlay.component.html',
  styleUrl: './viewport-overlay.component.css',
})
export class ViewportOverlayComponent {
  pane = input.required<ViewPane>();

  protected layout      = inject(SplitLayoutStoreService);
  protected dataService = inject(PointCloudDataService);

  /** True when this is the only pane (cannot close). */
  protected isLastPane = computed(() => this.layout.paneCount() <= 1);

  /** True when there is no point cloud data loaded. */
  protected hasData = computed(() => this.dataService.frames().size > 0);

  /**
   * True when LOD is active: multiple panes present and this pane is small
   * (< 50% of the layout space).
   */
  protected adaptiveLodActive = computed(() =>
    this.layout.paneCount() > 1 && this.pane().sizeFraction < 0.5,
  );

  readonly orientationOptions: OrientationOption[] = [
    { value: 'perspective', label: 'Perspective' },
    { value: 'top',         label: 'Top'         },
    { value: 'front',       label: 'Front'       },
    { value: 'side',        label: 'Side'        },
  ];

  changeOrientation(event: Event): void {
    const value = (event.target as HTMLSelectElement | HTMLInputElement).value as ViewOrientation;
    this.layout.setPaneOrientation(this.pane().id, value);
  }

  closePane(): void {
    if (!this.isLastPane()) {
      this.layout.removePane(this.pane().id);
    }
  }
}
