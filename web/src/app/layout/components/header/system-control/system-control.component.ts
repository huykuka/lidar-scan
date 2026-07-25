import {ChangeDetectionStrategy, Component, computed, inject, signal} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {SystemStatusService} from '@core/services/system-status.service';
import {AuthService} from '@core/services/auth.service';
import {ToastService} from '@core/services/toast.service';

/**
 * System start/stop toggle button for the header.
 * Uses the same pattern as ConnectionStatusComponent: --status-color CSS variable
 * driven by computed state, with Synergy token colors.
 */
@Component({
  selector: 'app-system-control',
  imports: [SynergyComponentsModule],
  templateUrl: './system-control.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
    }
  `,
})
export class SystemControlComponent {
  private readonly systemStatus = inject(SystemStatusService);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);

  protected readonly isRunning = this.systemStatus.isRunning;
  protected readonly canEdit = this.auth.canEdit;
  protected readonly loading = signal(false);

  protected readonly icon = computed(() =>
    this.isRunning() ? 'play_circle' : 'motion_photos_paused',
  );

  protected readonly label = computed(() =>
    this.isRunning() ? 'System running — click to stop' : 'System stopped — click to start',
  );

  protected readonly statusColor = computed(() =>
    this.isRunning()
      ? 'var(--syn-color-success-600)'
      : 'var(--syn-color-error-600)',
  );

  protected async onToggle(): Promise<void> {
    this.loading.set(true);
    try {
      if (this.isRunning()) {
        await this.systemStatus.stopSystem();
        this.toast.success('Data flow stopped.');
      } else {
        await this.systemStatus.startSystem();
        this.toast.success('Data flow started.');
      }
    } catch {
      this.toast.danger(
        this.isRunning() ? 'Failed to stop data flow.' : 'Failed to start data flow.',
      );
    } finally {
      this.loading.set(false);
    }
  }
}
