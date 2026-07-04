import {ChangeDetectionStrategy, Component, inject} from '@angular/core';
import {Router} from '@angular/router';
import {SynIconComponent} from '@synergy-design-system/angular';

import {DrawerService} from '@core/services/drawer.service';

@Component({
  selector: 'app-start-guide-drawer',
  imports: [SynIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: [
    `
      :host {
        display: block;
      }
      .guide-hero {
        background:
          radial-gradient(
            circle at top right,
            color-mix(in srgb, var(--syn-color-primary-200) 45%, transparent) 0%,
            transparent 60%
          ),
          linear-gradient(180deg, var(--syn-color-neutral-25), var(--syn-color-neutral-50));
      }
      .guide-card {
        border: 1px solid var(--syn-color-neutral-200);
        background: var(--syn-color-neutral-50);
        transition:
          transform 160ms ease,
          border-color 160ms ease,
          box-shadow 160ms ease;
      }
      .guide-card:hover {
        transform: translateY(-2px);
        border-color: var(--syn-color-primary-400);
        box-shadow: var(--syn-shadow-level-1);
      }
      .guide-chip {
        border: 1px solid var(--syn-color-primary-200);
        background: var(--syn-color-primary-50);
        color: var(--syn-color-primary-700);
      }
    `,
  ],
  template: `
    <div class="w-full overflow-auto p-1 sm:p-2">
      <div class="w-full mx-auto space-y-5 sm:space-y-6">
        <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 sm:gap-4">
          <div
            (click)="navigateTo('/workspaces')"
            class="guide-card p-4 sm:p-5 md:p-6 rounded-xl cursor-pointer"
          >
            <syn-icon
              class="text-syn-color-primary-600 text-2xl sm:text-3xl mb-2 sm:mb-3"
              name="home"
            />
            <h3 class="font-bold text-syn-typography-color-text mb-1 sm:mb-2 text-sm sm:text-base">
              Workspaces
            </h3>
            <p class="text-xs sm:text-sm mb-2 sm:mb-3 leading-relaxed">
              Visualize live point cloud streams in interactive 3D workspaces with real-time
              rendering.
            </p>
          </div>

          <div
            (click)="navigateTo('/settings')"
            class="guide-card p-4 sm:p-5 md:p-6 rounded-xl cursor-pointer"
          >
            <syn-icon
              class="text-syn-color-primary-600 text-2xl sm:text-3xl mb-2 sm:mb-3"
              name="settings"
            />
            <h3 class="font-bold text-syn-typography-color-text mb-1 sm:mb-2 text-sm sm:text-base">
              Settings
            </h3>
            <p class="text-xs sm:text-sm mb-2 sm:mb-3 leading-relaxed">
              Build processing graphs with drag-and-drop nodes. Configure sensors, fusion, and
              pipeline operations.
            </p>
          </div>

          <div
            (click)="navigateTo('/recordings')"
            class="guide-card p-4 sm:p-5 md:p-6 rounded-xl cursor-pointer"
          >
            <syn-icon
              class="text-syn-color-primary-600 text-2xl sm:text-3xl mb-2 sm:mb-3"
              name="video_library"
            />
            <h3 class="font-bold text-syn-typography-color-text mb-1 sm:mb-2 text-sm sm:text-base">
              Recordings
            </h3>
            <p class="text-xs sm:text-sm mb-2 sm:mb-3 leading-relaxed">
              Manage recorded point cloud sessions. Play back, export, and analyze historical data.
            </p>
          </div>

          <div
            (click)="navigateTo('/results')"
            class="guide-card p-4 sm:p-5 md:p-6 rounded-xl cursor-pointer"
          >
            <syn-icon
              class="text-syn-color-primary-600 text-2xl sm:text-3xl mb-2 sm:mb-3"
              name="analytics"
            />
            <h3 class="font-bold text-syn-typography-color-text mb-1 sm:mb-2 text-sm sm:text-base">
              Results
            </h3>
            <p class="text-xs sm:text-sm mb-2 sm:mb-3 leading-relaxed">
              Explore node outputs, inspect metadata, and review generated artifacts including point
              cloud result files.
            </p>
          </div>

          <div
            (click)="navigateTo('/calibration')"
            class="guide-card p-4 sm:p-5 md:p-6 rounded-xl cursor-pointer"
          >
            <syn-icon
              class="text-syn-color-primary-600 text-2xl sm:text-3xl mb-2 sm:mb-3"
              name="tune"
            />
            <h3 class="font-bold text-syn-typography-color-text mb-1 sm:mb-2 text-sm sm:text-base">
              Calibration
            </h3>
            <p class="text-xs sm:text-sm mb-2 sm:mb-3 leading-relaxed">
              Run and review calibration workflows to align sensors and improve fusion quality
              across your setup.
            </p>
          </div>

          <div
            (click)="navigateTo('/logs')"
            class="guide-card p-4 sm:p-5 md:p-6 rounded-xl cursor-pointer"
          >
            <syn-icon
              class="text-syn-color-primary-600 text-2xl sm:text-3xl mb-2 sm:mb-3"
              name="description"
            />
            <h3 class="font-bold text-syn-typography-color-text mb-1 sm:mb-2 text-sm sm:text-base">
              Logs
            </h3>
            <p class="text-xs sm:text-sm mb-2 sm:mb-3 leading-relaxed">
              Monitor backend/runtime activity and troubleshoot with structured log streams for
              errors, warnings, and operations.
            </p>
          </div>
        </div>

        <div class="mt-2 sm:mt-3 rounded-2xl border border-syn-color-neutral-200 p-4 sm:p-5">
          <h3 class="text-base sm:text-lg font-bold text-syn-typography-color-text mb-3 sm:mb-4">
            Getting Started
          </h3>
          <ol class="space-y-2 sm:space-y-2.5 text-xs sm:text-sm text-syn-typography-color-text">
            <li>1. Configure sensors and runtime behavior in <strong>Settings</strong>.</li>
            <li>2. Build your node graph and connect pipeline stages.</li>
            <li>3. Calibrate alignment before running multi-sensor fusion.</li>
            <li>
              4. Validate live data in <strong>Workspaces</strong> and inspect outcomes in
              <strong>Results</strong>.
            </li>
            <li>
              5. Record sessions for replay and audit in <strong>Recordings</strong> and
              <strong>Logs</strong>.
            </li>
          </ol>
        </div>
      </div>
    </div>
  `,
})
export class StartGuideDrawerComponent {
  private readonly router = inject(Router);
  private readonly drawer = inject(DrawerService);

  protected navigateTo(route: string): void {
    this.drawer.close();
    void this.router.navigate([route]);
  }
}
