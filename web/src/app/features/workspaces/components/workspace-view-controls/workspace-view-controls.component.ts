import { Component, inject, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { WorkspaceStoreService } from '../../../../core/services/stores/workspace-store.service';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { WorkspaceViewControlsButtonComponent } from './workspace-view-controls-button.component';

@Component({
  selector: 'app-workspace-view-controls',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule, WorkspaceViewControlsButtonComponent],
  template: `
    <div
      class="absolute bottom-4 left-1/2 -translate-x-1/2 opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity duration-300"
    >
      <div
        class="flex items-center gap-1 bg-black/40 backdrop-blur-xl p-1.5 rounded-2xl border border-white/15 shadow-2xl"
      >
        <app-workspace-view-controls-button
          [label]="showHud() ? 'Hide HUD' : 'Show HUD'"
          [icon]="showHud() ? 'visibility_off' : 'visibility'"
          [active]="showHud()"
          (clicked)="toggleHud()"
        ></app-workspace-view-controls-button>

        <app-workspace-view-controls-button
          label="Grid"
          icon="grid_on"
          [active]="showGrid()"
          (clicked)="toggleGrid()"
        ></app-workspace-view-controls-button>

        <app-workspace-view-controls-button
          label="Axes"
          icon="trip_origin"
          [active]="showAxes()"
          (clicked)="toggleAxes()"
        ></app-workspace-view-controls-button>

        <div class="w-px h-6 bg-white/15 mx-1"></div>

        <app-workspace-view-controls-button
          label="Reset View"
          icon="center_focus_strong"
          (clicked)="onResetCamera.emit()"
        ></app-workspace-view-controls-button>

        <app-workspace-view-controls-button
          label="Screenshot"
          icon="photo_camera"
          (clicked)="onScreenshot.emit()"
        ></app-workspace-view-controls-button>

        <app-workspace-view-controls-button
          label="Clear Points"
          icon="delete_sweep"
          (clicked)="onClearPoints.emit()"
        ></app-workspace-view-controls-button>
      </div>
    </div>
  `,
  styles: [
    `
      .backdrop-blur-xl {
        backdrop-filter: blur(24px);
      }
    `,
  ],
})
export class WorkspaceViewControlsComponent {
  private store = inject(WorkspaceStoreService);

  protected showHud = this.store.showHud;
  protected showGrid = this.store.showGrid;
  protected showAxes = this.store.showAxes;

  onResetCamera = output<void>();
  onScreenshot = output<void>();
  onClearPoints = output<void>();

  toggleHud() {
    this.store.set('showHud', !this.showHud());
  }

  toggleGrid() {
    this.store.set('showGrid', !this.showGrid());
  }

  toggleAxes() {
    this.store.set('showAxes', !this.showAxes());
  }
}
