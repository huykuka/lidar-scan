import { Component, computed, inject, output, ChangeDetectionStrategy } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { SystemStatusService } from '@core/services/system-status.service';

/**
 * System notices / error badge.
 * Icons: sick2025 iconset (outline variants — confirmed via Synergy MCP):
 *   - idle:    circle_notifications
 *   - warning: notification_important
 *   - error:   error
 * Size: large — syn-icon-button size="large".
 * Icon color and badge color both reflect the highest active notice level
 * via --status-color CSS variable.
 */
@Component({
  selector: 'app-notices-status',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './notices-status.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host {
      display: inline-flex;
      position: relative;
      align-items: center;
    }
    syn-icon-button {
      color: var(--status-color);
    }
  `,
})
export class NoticesStatusComponent {
  readonly acknowledge = output<void>();

  private readonly svc = inject(SystemStatusService);

  protected readonly unreadCount = this.svc.unreadCount;
  protected readonly lastNotice = this.svc.lastNotice;

  /** sick2025 outline icons — confirmed via Synergy MCP */
  protected readonly icon = computed(() => {
    const notice = this.lastNotice();
    if (!notice) return 'circle_notifications';
    if (notice.level === 'error') return 'error';
    if (notice.level === 'warning') return 'notification_important';
    return 'circle_notifications';
  });

  protected readonly label = computed(() => {
    const notice = this.lastNotice();
    if (!notice) return 'No notifications';
    return notice.message;
  });

  /** Badge text — cap at 9+ */
  protected readonly badgeText = computed(() => {
    const n = this.unreadCount();
    return n > 9 ? '9+' : String(n);
  });

  /**
   * Icon and badge color driven by the highest active notice level.
   * idle    → neutral-500 (grey)
   * warning → warning-600 (amber)
   * error   → danger-600  (red)
   */
  protected readonly statusColor = computed(() => {
    const notice = this.lastNotice();
    if (!notice || this.unreadCount() === 0) return 'var(--syn-color-neutral-500)';
    if (notice.level === 'error') return 'var(--syn-color-error-600)';
    if (notice.level === 'warning') return 'var(--syn-color-warning-600)';
    return 'var(--syn-color-neutral-500)';
  });

  protected onAcknowledge(): void {
    this.acknowledge.emit();
  }
}
