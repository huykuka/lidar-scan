import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
} from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { SplitLayoutStoreService, ViewOrientation } from '@core/services/split-layout-store.service';

interface ViewTypeEntry {
  value: ViewOrientation;
  label: string;
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

  /** Exposed as a computed so the template and tests can read it easily. */
  canAdd = computed(() => this.layout.canAddPane());

  readonly viewTypes: ViewTypeEntry[] = [
    { value: 'perspective', label: 'Perspective', icon: '3d_rotation'   },
    { value: 'top',         label: 'Top',         icon: 'vertical_align_top' },
    { value: 'front',       label: 'Front',       icon: 'front_hand'    },
    { value: 'side',        label: 'Side',        icon: 'side_navigation' },
  ];

  addView(orientation: ViewOrientation): void {
    this.layout.addPane(orientation);
  }

  resetLayout(): void {
    this.layout.resetToDefault();
  }
}
