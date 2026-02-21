import { Component, inject, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { WorkspaceStoreService } from '../../../../core/services/stores/workspace-store.service';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

@Component({
  selector: 'app-workspace-view-controls',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  template: `
    <div
      class="absolute bottom-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-300"
    >
      <div
        class="flex items-center gap-2 bg-black/40 backdrop-blur-xl p-2 rounded-2xl border border-white/20 shadow-2xl"
      >
        <syn-button variant="text" size="small" (click)="toggleHud()" class="text-white">
          <syn-icon slot="prefix" [name]="showHud() ? 'visibility_off' : 'visibility'"></syn-icon>
          {{ showHud() ? 'Hide HUD' : 'Show HUD' }}
        </syn-button>
        <syn-button variant="text" size="small" (click)="onResetCamera.emit()" class="text-white">
          <syn-icon slot="prefix" name="center_focus_strong"></syn-icon>
          Reset View
        </syn-button>
        <syn-button variant="text" size="small" (click)="onClearPoints.emit()" class="text-white">
          <syn-icon slot="prefix" name="delete_sweep"></syn-icon>
          Clear
        </syn-button>
      </div>
    </div>
  `,
  styles: [
    `
      .text-white {
        --syn-button-color-outline: #ffffff;
        --syn-button-color-text: #ffffff;
        color: #ffffff;
      }
      .text-white syn-icon {
        color: #ffffff;
      }
      .backdrop-blur-xl {
        backdrop-filter: blur(24px);
      }
    `,
  ],
})
export class WorkspaceViewControlsComponent {
  private store = inject(WorkspaceStoreService);

  protected showHud = this.store.showHud;
  onResetCamera = output();
  onClearPoints = output();

  toggleHud() {
    this.store.set('showHud', !this.showHud());
  }
}
