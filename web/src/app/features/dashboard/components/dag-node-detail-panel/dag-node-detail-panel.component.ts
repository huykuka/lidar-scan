import { Component, input, output, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  SynCardComponent,
  SynBadgeComponent,
  SynIconButtonComponent,
} from '@synergy-design-system/angular';
import { DagNodeMetrics } from '../../../../core/models/metrics.model';

/**
 * Detailed stats panel for a single selected DAG node
 * Shown when a row in the overview table is clicked
 */
@Component({
  selector: 'app-dag-node-detail-panel',
  standalone: true,
  imports: [CommonModule, SynCardComponent, SynBadgeComponent, SynIconButtonComponent],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './dag-node-detail-panel.component.html',
  styleUrl: './dag-node-detail-panel.component.css',
})
export class DagNodeDetailPanelComponent {
  // Signal input
  node = input<DagNodeMetrics | null>(null);

  // Output for close action
  closeDetail = output<void>();

  onClose(): void {
    this.closeDetail.emit();
  }

  formatThroughput(pps: number): string {
    if (pps >= 1000) {
      return `${(pps / 1000).toFixed(1)}k pts/s`;
    }
    return `${pps.toFixed(0)} pts/s`;
  }

  formatLastSeen(timestamp: number): string {
    if (!timestamp) return 'Never';

    const now = Date.now() / 1000;
    const secondsAgo = Math.floor(now - timestamp);

    if (secondsAgo < 60) {
      return `${secondsAgo}s ago`;
    } else if (secondsAgo < 3600) {
      return `${Math.floor(secondsAgo / 60)}m ago`;
    } else {
      return `${Math.floor(secondsAgo / 3600)}h ago`;
    }
  }

  formatAbsoluteTime(timestamp: number): string {
    if (!timestamp) return '';
    return new Date(timestamp * 1000).toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
  }
}
