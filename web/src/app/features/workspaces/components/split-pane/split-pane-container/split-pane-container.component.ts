import {Component, computed, effect, inject, signal} from '@angular/core';
import {SplitGroup, SplitLayoutStoreService, LayoutMode, ViewPane} from '@core/services/split-layout-store.service';
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
  protected isGridLayout   = computed(() => this.layout.layoutMode() === '4-grid');
  protected isOneTwoLayout = computed(() => this.layout.layoutMode() === '1+2');

  /** All panes flattened — used by the grid template */
  protected allPanes = computed(() => this.layout.allPanes());

  /** Outer column fractions for 1+2 layout */
  protected oneTwoFractions = computed(() => this.layout.oneTwoColumnFractions());

  /**
   * True only for one animation cycle after the layout MODE changes.
   * Fraction/pane-count updates within the same mode do NOT set this.
   * Resets itself automatically when the animation ends (see template).
   */
  protected animateEnter = signal(false);

  private prevMode: LayoutMode | null = null;

  constructor() {
    // Fire the enter animation only when the layout mode itself changes,
    // not when sizeFraction values are updated (e.g. after a drag).
    effect(() => {
      const mode = this.layout.layoutMode();
      if (mode !== this.prevMode) {
        this.prevMode = mode;
        // Toggle off→on so the animation re-triggers even for the same class
        this.animateEnter.set(false);
        // Microtask flush ensures the class removal is rendered before re-adding
        queueMicrotask(() => this.animateEnter.set(true));
      }
    });
  }

  /** Called by (animationend) on the layout wrapper — removes the class once done. */
  protected onEnterAnimationEnd(): void {
    this.animateEnter.set(false);
  }

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
   * but changes when the layout mode changes so Angular updates the DOM.
   */
  groupKey(group: SplitGroup, index: number): string {
    return `${index}-${group.axis}-${group.panes.length}`;
  }
}
