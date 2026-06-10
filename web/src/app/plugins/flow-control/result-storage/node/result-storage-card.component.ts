import { Component, computed, input } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeCardComponent } from '@core/models/node-plugin.model';
import { CanvasNode } from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import { NodeStatusUpdate } from '@core/models/node-status.model';

/**
 * Canvas card component for Result Storage nodes.
 * Displays the configured default status as a compact badge.
 */
@Component({
  selector: 'app-result-storage-card',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './result-storage-card.component.html',
})
export class ResultStorageCardComponent implements NodeCardComponent {
  node = input.required<CanvasNode>();
  status = input<NodeStatusUpdate | null>(null);

  protected statusLabel = computed(() => {
    const s = this.node().data.config?.['default_status'] ?? 'success';
    return s.charAt(0).toUpperCase() + s.slice(1);
  });

  protected statusVariant = computed(() => {
    const s = this.node().data.config?.['default_status'] ?? 'success';
    const map: Record<string, string> = {
      success: 'success',
      warning: 'warning',
      error: 'danger',
    };
    return map[s] ?? 'neutral';
  });
}
