import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
} from '@angular/core';
import { SplitLayoutStoreService, SplitGroup, ViewPane } from '@core/services/split-layout-store.service';
import { WorkspaceStoreService } from '@core/services/stores/workspace-store.service';
import { PointCloudComponent } from '../../point-cloud/point-cloud.component';
import { ViewportOverlayComponent } from '../../viewport-overlay/viewport-overlay.component';
import { ResizableDividerDirective } from '../resizable-divider.directive';

@Component({
  selector: 'app-split-pane-container',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [PointCloudComponent, ViewportOverlayComponent, ResizableDividerDirective],
  templateUrl: './split-pane-container.component.html',
  styleUrl: './split-pane-container.component.css',
})
export class SplitPaneContainerComponent {
  protected layout = inject(SplitLayoutStoreService);
  protected store  = inject(WorkspaceStoreService);

  protected groups   = computed(() => this.layout.groups());
  protected paneCount = computed(() => this.layout.paneCount());

  /** CSS class for the flex direction of a group */
  groupClass(group: SplitGroup): string {
    return group.axis === 'horizontal'
      ? 'flex flex-row w-full h-full'
      : 'flex flex-col w-full h-full';
  }

  /**
   * A pane is "small" (needs LOD) if there are multiple panes
   * and this pane takes up less than 50% of the layout.
   */
  isSmallPane(pane: ViewPane): boolean {
    return this.paneCount() > 1 && pane.sizeFraction < 0.5;
  }

  /** Inline flex style for a single pane div */
  paneStyle(pane: ViewPane): Record<string, string> {
    return { flex: String(pane.sizeFraction) };
  }
}
