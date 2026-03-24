import {Component, computed, inject, output} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {SystemStatusService} from '@core/services/system-status.service';

/**
 * System notices / error badge.
 * Icons: sick2025 iconset (outline variants — confirmed via Synergy MCP):
 *   - idle:    circle_notifications
 *   - warning: notification_important
 *   - error:   error
 * Size: large — syn-icon-button size="large".
 * Badge uses --syn-color-danger-600 token.
 */
@Component({
  selector: 'app-notices-status',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './notices-status.component.html',
  styles: `
    :host {
      display: inline-flex;
      position: relative;
      align-items: center;
    }
    syn-icon-button {
      color: var(--syn-color-neutral-500);
      transition: color 0.15s ease;
    }
    :host:hover syn-icon-button {
      color: var(--syn-color-primary-600);
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

  protected onAcknowledge(): void {
    this.acknowledge.emit();
  }
}
