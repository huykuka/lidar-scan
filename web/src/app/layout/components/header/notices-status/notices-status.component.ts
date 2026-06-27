import { Component, computed, inject, output, signal, ChangeDetectionStrategy } from '@angular/core';
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
  imports: [SynergyComponentsModule],
  templateUrl: './notices-status.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host {
      display: inline-flex;
      position: relative;
      align-items: center;
    }
    syn-icon-button {
      color: var(--status-color);
    }
    .notice-panel {
      min-width: 220px;
      max-width: 320px;
      padding: 12px 14px;
    }
    .notice-row {
      display: flex;
      align-items: flex-start;
      gap: 8px;
    }
    .notice-icon {
      flex-shrink: 0;
      color: var(--status-color);
      font-size: 18px;
      margin-top: 1px;
    }
    .notice-message {
      font-size: var(--syn-font-size-small);
      line-height: 1.4;
      color: var(--syn-color-neutral-900);
    }
    .notice-empty {
      font-size: var(--syn-font-size-small);
      color: var(--syn-color-neutral-500);
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
    if (notice.level === 'error') return 'dangerous';
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

  protected readonly dropdownOpen = signal(false);

  protected onDropdownShow(): void {
    this.dropdownOpen.set(true);
  }

  protected onDropdownHide(): void {
    this.dropdownOpen.set(false);
    this.svc.acknowledge();
    this.acknowledge.emit();
  }
}
