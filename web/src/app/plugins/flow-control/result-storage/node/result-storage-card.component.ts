import { Component, computed, input } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeCardComponent } from '@core/models/node-plugin.model';
import { CanvasNode } from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import { NodeStatusUpdate } from '@core/models/node-status.model';

@Component({
  selector: 'app-result-storage-card',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './result-storage-card.component.html',
})
export class ResultStorageCardComponent implements NodeCardComponent {
  node = input.required<CanvasNode>();
  status = input<NodeStatusUpdate | null>(null);

  protected colorCount = computed(() => {
    const map = this.node().data.config?.['color_map'];
    return map && typeof map === 'object' ? Object.keys(map).length : 0;
  });
}
