import {Component, computed, inject,} from '@angular/core';
import {SplitGroup, SplitLayoutStoreService, ViewPane} from '@core/services/split-layout-store.service';
import {WorkspaceStoreService} from '@core/services/stores/workspace-store.service';
import {PointCloudComponent} from '../../point-cloud/point-cloud.component';
import {ViewportOverlayComponent} from '../../viewport-overlay/viewport-overlay.component';
import {ResizableDividerDirective} from '../resizable-divider.directive';

@Component({
  selector: 'app-split-pane-container',
  imports: [PointCloudComponent, ViewportOverlayComponent, ResizableDividerDirective],
  templateUrl: './split-pane-container.component.html',
  styleUrl: './split-pane-container.component.css',
})
export class SplitPaneContainerComponent {
  protected layout = inject(SplitLayoutStoreService);
  protected store  = inject(WorkspaceStoreService);

  protected groups     = computed(() => this.layout.groups());
  protected paneCount  = computed(() => this.layout.paneCount());
  protected layoutMode = computed(() => this.layout.layoutMode());

  /** True when the active layout is the 2×2 grid preset */
  protected isGridLayout  = computed(() => this.layout.layoutMode() === '4-grid');
  protected isOneTwoLayout = computed(() => this.layout.layoutMode() === '1+2');

  /** All panes flattened — used by the grid template */
  protected allPanes = computed(() => this.layout.allPanes());

  /** Outer column fractions for 1+2 layout */
  protected oneTwoFractions = computed(() => this.layout.oneTwoColumnFractions());

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

  /** Inline flex style for a single pane div (flex layouts only) */
  paneStyle(pane: ViewPane): Record<string, string> {
    return { flex: String(pane.sizeFraction) };
  }

  /**
   * Track expression for groups — stable enough to avoid canvas recreation,
   * but changes when the layout mode changes so the wrapper div re-animates.
   */
  groupKey(group: SplitGroup, index: number): string {
    return `${index}-${group.axis}-${group.panes.length}`;
  }
}
