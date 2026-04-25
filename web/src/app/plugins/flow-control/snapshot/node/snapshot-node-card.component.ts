import { Component, computed, input } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeCardComponent } from '@core/models/node-plugin.model';
import { CanvasNode } from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import { NodeStatusUpdate } from '@core/models/node-status.model';

/**
 * Canvas card component for Snapshot Nodes.
 * Displays the configured throttle interval as a compact badge.
 */
@Component({
  selector: 'app-snapshot-node-card',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './snapshot-node-card.component.html',
  styleUrl: './snapshot-node-card.component.css',
})
export class SnapshotNodeCardComponent implements NodeCardComponent {
  node = input.required<CanvasNode>();
  status = input<NodeStatusUpdate | null>(null);

  /**
   * Human-readable throttle label shown on the canvas card.
   */
  protected throttleLabel = computed(() => {
    const ms = this.node().data.config?.['throttle_ms'] ?? 0;
    return ms > 0 ? `${ms} ms` : 'No throttle';
  });
}
