import {Component, computed, input} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NodeCardComponent} from '@core/models/node-plugin.model';
import {CanvasNode} from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import {NodeStatusUpdate} from '@core/models/node-status.model';

/**
 * Canvas card component for Output Nodes.
 * Shows webhook-enabled indicator and a "View Data" badge.
 */
@Component({
  selector: 'app-output-node-card',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './output-node-card.component.html',
  styleUrl: './output-node-card.component.css',
})
export class OutputNodeCardComponent implements NodeCardComponent {
  node = input.required<CanvasNode>();
  status = input<NodeStatusUpdate | null>(null);

  protected webhookEnabled = computed(() => !!this.node().data.config?.['webhook_enabled']);
}
