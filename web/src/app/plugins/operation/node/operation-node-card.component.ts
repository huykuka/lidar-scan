import {Component, computed, CUSTOM_ELEMENTS_SCHEMA, input} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CanvasNode} from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import {NodeStatusUpdate} from '@core/models/node-status.model';
import {NodeCardComponent} from '@core/models/node-plugin.model';

@Component({
  selector: 'app-operation-node-card',
  standalone: true,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [SynergyComponentsModule],
  templateUrl: './operation-node-card.component.html',
  styleUrl: './operation-node-card.component.css',
})
export class OperationNodeCardComponent implements NodeCardComponent {
  node = input.required<CanvasNode>();
  status = input<NodeStatusUpdate | null>(null);

  protected operationType = computed(() => {
    return this.node().data.config['op_type'] || 'unknown';
  });

  protected operationConfig = computed(() => {
    const config = this.node().data.config['op_config'] || {};
    return Object.entries(config).map(([key, value]) => ({
      key,
      value: this.formatValue(value),
    }));
  });

  protected hasConfig = computed(() => this.operationConfig().length > 0);

  private formatValue(value: any): string {
    if (value === null || value === undefined) return '-';
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (Array.isArray(value)) return `[${value.join(', ')}]`;
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }
}
