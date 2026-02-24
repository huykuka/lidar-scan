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
      class="absolute left-4 top-0 bottom-0 flex flex-col justify-center items-start opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity duration-300 py-2 sm:py-4 pointer-events-none z-50"
    >
      <div
        class="flex flex-col items-center justify-center gap-1 bg-black/40 backdrop-blur-xl p-1.5 rounded-2xl border border-white/15 shadow-2xl pointer-events-auto max-h-full overflow-y-auto"
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

        <div class="h-px w-6 bg-white/15 my-1 hidden sm:block"></div>

        <!-- Camera View Presets -->
        <app-workspace-view-controls-button
          label="Top View"
          icon="vertical_align_top"
          (clicked)="onTopView.emit()"
        ></app-workspace-view-controls-button>

        <app-workspace-view-controls-button
          label="Front View"
          icon="view_agenda"
          (clicked)="onFrontView.emit()"
        ></app-workspace-view-controls-button>

        <app-workspace-view-controls-button
          label="Side View"
          icon="view_sidebar"
          (clicked)="onSideView.emit()"
        ></app-workspace-view-controls-button>

        <app-workspace-view-controls-button
          label="Isometric"
          icon="view_in_ar"
          (clicked)="onIsometricView.emit()"
        ></app-workspace-view-controls-button>

        <app-workspace-view-controls-button
          label="Fit to Points"
          icon="fit_screen"
          (clicked)="onFitToPoints.emit()"
        ></app-workspace-view-controls-button>

        <div class="h-px w-6 bg-white/15 my-1 hidden sm:block"></div>

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
          [danger]="true"
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
  onTopView = output<void>();
  onFrontView = output<void>();
  onSideView = output<void>();
  onIsometricView = output<void>();
  onFitToPoints = output<void>();
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
