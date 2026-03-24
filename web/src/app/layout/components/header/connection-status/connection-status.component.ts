import {Component, computed, inject, output} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {SystemStatusService} from '@core/services/system-status.service';

/**
 * Backend connectivity indicator.
 * Icons: sick2025 iconset (wifi / wifi_off / signal_wifi_0_bar — outline variants).
 * Size: large — syn-icon-button size="large" → font-size: var(--syn-font-size-2x-large).
 * Color: driven by CSS custom property --status-color on the host, applied via style binding
 * so we respect Synergy's token system without relying on Tailwind color utilities.
 * Status colors are always visible (no hover override — ConnectionStatus uses green/red/grey).
 */
@Component({
  selector: 'app-connection-status',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './connection-status.component.html',
  styles: `
    .status-dot {
      background-color: var(--status-color);
    }
  `,
})
export class ConnectionStatusComponent {
  readonly refresh = output<void>();

  private readonly svc = inject(SystemStatusService);

  protected readonly online = this.svc.backendOnline;
  protected readonly version = this.svc.backendVersion;

  /** sick2025 wifi icons — outline variants */
  protected readonly icon = computed(() => {
    const o = this.online();
    if (o === null) return 'signal_wifi_0_bar'; // checking/unknown
    return o ? 'leak_add' : 'leak_remove';
  });

  protected readonly label = computed(() => {
    const o = this.online();
    const v = this.version();
    if (o === null) return 'Checking backend…';
    if (o) return v ? `Backend Online — v${v}` : 'Backend Online';
    return 'Backend Offline — click to retry';
  });

  /** Synergy CSS token for status color, applied as inline CSS variable */
  protected readonly statusColor = computed(() => {
    const o = this.online();
    if (o === null) return 'var(--syn-color-neutral-500)';
    return o ? 'var(--syn-color-success-600)' : 'var(--syn-color-danger-600)';
  });

  protected onRefresh(): void {
    this.refresh.emit();
  }
}
