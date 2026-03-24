import { Component, computed, input } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeCardComponent } from '@core/models/node-plugin.model';
import { CanvasNode } from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import { NodeStatusUpdate } from '@core/models/node-status.model';
import { IfNodeStatus } from '@core/models/flow-control.model';

/**
 * Card component for IF Condition nodes displayed on the flow canvas
 * Shows expression preview and evaluation status badge
 */
@Component({
  selector: 'app-if-condition-card',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './if-condition-card.component.html',
  styleUrl: './if-condition-card.component.css',
})
export class IfConditionCardComponent implements NodeCardComponent {
  node = input.required<CanvasNode>();
  status = input<NodeStatusUpdate | null>(null);

  /**
   * Type-cast status to IfNodeStatus for accessing IF-specific fields
   */
  protected ifStatus = computed(() => this.status() as IfNodeStatus | null);

  /**
   * Truncate long expressions to 30 characters
   */
  protected shortExpression = computed(() => {
    const expr = this.node().data.config?.['expression'] || 'true';
    return expr.length > 30 ? expr.substring(0, 27) + '...' : expr;
  });
}
