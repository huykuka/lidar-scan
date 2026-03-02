import { Component, input, output, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynCardComponent, SynBadgeComponent } from '@synergy-design-system/angular';
import { DagNodeMetrics } from '../../../../core/models/metrics.model';

/**
 * Dumb panel displaying an overview table of all DAG nodes and their key metrics
 * No service injections - receives all data via inputs
 */
@Component({
  selector: 'app-dag-overview-panel',
  standalone: true,
  imports: [CommonModule, SynCardComponent, SynBadgeComponent],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './dag-overview-panel.component.html',
  styleUrl: './dag-overview-panel.component.css',
})
export class DagOverviewPanelComponent {
  // Signal inputs
  nodes = input<DagNodeMetrics[]>([]);
  totalNodes = input<number>(0);
  runningNodes = input<number>(0);

  // Output for node selection
  nodeSelected = output<DagNodeMetrics>();

  onNodeClick(node: DagNodeMetrics): void {
    this.nodeSelected.emit(node);
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
}
