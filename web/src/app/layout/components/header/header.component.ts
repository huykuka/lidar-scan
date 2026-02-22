import { Component, ViewChild, computed, inject, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule, SynHeaderComponent } from '@synergy-design-system/angular';
import { SystemStatusService } from '../../../core/services/system-status.service';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './header.component.html',
  styleUrl: './header.component.css',
})
export class HeaderComponent {
  private systemStatus = inject(SystemStatusService);

  label = input<string>('Synergy');
  @ViewChild('header', { static: true }) synHeader!: SynHeaderComponent;

  protected readonly backendOnline = this.systemStatus.backendOnline;
  protected readonly backendLabel = this.systemStatus.backendLabel;
  protected readonly backendVersion = this.systemStatus.backendVersion;
  protected readonly activeSensors = this.systemStatus.activeSensors;
  protected readonly unreadCount = this.systemStatus.unreadCount;
  protected readonly lastNotice = this.systemStatus.lastNotice;

  protected readonly statusDotClass = computed(() => {
    const online = this.backendOnline();
    if (online === null) return 'bg-syn-color-neutral-300';
    return online ? 'bg-syn-color-success-500' : 'bg-syn-color-danger-500';
  });

  protected readonly statusPillClass = computed(() => {
    const online = this.backendOnline();
    if (online === null) return 'border-syn-color-neutral-200 bg-white';
    return online
      ? 'border-syn-color-success-200 bg-syn-color-success-50'
      : 'border-syn-color-danger-200 bg-syn-color-danger-50';
  });

  protected readonly noticeIcon = computed(() => {
    const notice = this.lastNotice();
    if (!notice) return 'info';
    if (notice.level === 'error') return 'error';
    if (notice.level === 'warning') return 'warning';
    return 'info';
  });

  protected readonly noticeText = computed(() => {
    const notice = this.lastNotice();
    return notice?.message || 'No notifications';
  });

  protected acknowledgeNotices() {
    this.systemStatus.acknowledge();
  }

  protected refreshStatus() {
    this.systemStatus.refreshNow();
  }

  get nativeElement() {
    return this.synHeader.nativeElement;
  }
}
