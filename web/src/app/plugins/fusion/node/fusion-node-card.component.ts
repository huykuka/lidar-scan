import {Component, computed, CUSTOM_ELEMENTS_SCHEMA, input} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CanvasNode} from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import {NodeStatus} from '@core/models/node.model';
import {NodeCardComponent} from '@core/models/node-plugin.model';
import {inject} from '@angular/core';
import {NodeStoreService} from '@core/services/stores/node-store.service';

@Component({
  selector: 'app-fusion-node-card',
  standalone: true,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [SynergyComponentsModule],
  templateUrl: './fusion-node-card.component.html',
  styleUrl: './fusion-node-card.component.css',
})
export class FusionNodeCardComponent implements NodeCardComponent {
  node = input.required<CanvasNode>();
  status = input<NodeStatus | null>(null);
  private nodeStore = inject(NodeStoreService);

  protected sensorCount = computed(() => {
    const sensorIds = this.node().data.config['sensor_ids'] || [];
    return Array.isArray(sensorIds) ? sensorIds.length : 0;
  });

  protected sensorNames = computed(() => {
    const sensorIds = this.node().data.config['sensor_ids'] || [];
    const allNodes = this.nodeStore.nodes();
    return (sensorIds as string[]).map((id) => {
      const sensorNode = allNodes.find((n) => n.id === id);
      return sensorNode?.name || id;
    });
  });

  protected pipelineName = computed(() => {
    const name = this.node().data.config['pipeline_name'];
    if (!name || name === 'none') return null;
    return name;
  });

  protected topic = computed(() => {
    return this.node().data.config['topic'] || null;
  });
}
