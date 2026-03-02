import { Component, input, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  SynCardComponent,
  SynProgressBarComponent,
  SynBadgeComponent,
} from '@synergy-design-system/angular';
import { SystemMetrics } from '../../../../core/models/metrics.model';

/**
 * Panel showing OS-level system resource metrics
 * Uses progress bars and gauges to display CPU, memory, threads, and queue status
 */
@Component({
  selector: 'app-system-panel',
  standalone: true,
  imports: [CommonModule, SynCardComponent, SynProgressBarComponent, SynBadgeComponent],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './system-panel.component.html',
  styleUrl: './system-panel.component.css',
})
export class SystemPanelComponent {
  // Signal input
  systemMetrics = input<SystemMetrics | null>(null);

  getCpuColor(): string {
    const cpu = this.systemMetrics()?.cpu_percent || 0;
    if (cpu < 50) return 'var(--syn-color-success-600)';
    if (cpu < 80) return 'var(--syn-color-warning-600)';
    return 'var(--syn-color-danger-600)';
  }

  getCpuBadgeVariant(): 'success' | 'warning' | 'danger' | 'neutral' {
    const cpu = this.systemMetrics()?.cpu_percent || 0;
    if (cpu < 50) return 'success';
    if (cpu < 80) return 'warning';
    return 'danger';
  }

  getCpuStatusText(): string {
    const cpu = this.systemMetrics()?.cpu_percent || 0;
    if (cpu < 50) return 'Good';
    if (cpu < 80) return 'Moderate';
    return 'High';
  }

  getMemoryColor(): string {
    const memory = this.systemMetrics()?.memory_percent || 0;
    if (memory < 50) return 'var(--syn-color-success-600)';
    if (memory < 80) return 'var(--syn-color-warning-600)';
    return 'var(--syn-color-danger-600)';
  }

  formatMemoryUsage(): string {
    const metrics = this.systemMetrics();
    if (!metrics) return '';

    return `${metrics.memory_used_mb.toFixed(0)} / ${metrics.memory_total_mb.toFixed(0)} MB`;
  }

  getQueueBadgeVariant(): 'success' | 'warning' | 'danger' | 'neutral' {
    const depth = this.systemMetrics()?.queue_depth || 0;
    if (depth === 0) return 'success';
    if (depth <= 5) return 'neutral';
    if (depth <= 10) return 'warning';
    return 'danger';
  }

  getQueueStatusText(): string {
    const depth = this.systemMetrics()?.queue_depth || 0;
    if (depth === 0) return 'Empty';
    if (depth <= 5) return 'Normal';
    if (depth <= 10) return 'Busy';
    return 'Backlogged';
  }
}
