import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
} from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { SplitLayoutStoreService, LayoutMode } from '@core/services/split-layout-store.service';

interface LayoutPreset {
  id: LayoutMode;
  label: string;
  title: string;
  icon: string;
}

@Component({
  selector: 'app-view-toolbar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SynergyComponentsModule],
  templateUrl: './view-toolbar.component.html',
  styleUrl: './view-toolbar.component.css',
})
export class ViewToolbarComponent {
  protected layout = inject(SplitLayoutStoreService);

  /** Current active layout mode — drives button highlight */
  protected activeMode = computed(() => this.layout.layoutMode());

  readonly presets: LayoutPreset[] = [
    { id: 'single',  label: '1',   title: 'Single pane (perspective)',      icon: 'crop_square'       },
    { id: 'h-split', label: '2H',  title: 'Horizontal split (top/bottom)',  icon: 'horizontal_split'  },
    { id: 'v-split', label: '2V',  title: 'Vertical split (left/right)',    icon: 'vertical_split'    },
    { id: '4-grid',  label: '4',   title: '4-pane grid (2×2)',              icon: 'grid_view'         },
  ];

  applyPreset(id: LayoutMode): void {
    switch (id) {
      case 'single':  this.layout.resetToDefault();     break;
      case 'h-split': this.layout.setHorizontalSplit(); break;
      case 'v-split': this.layout.setVerticalSplit();   break;
      case '4-grid':  this.layout.setFourPaneGrid();    break;
    }
  }
}
