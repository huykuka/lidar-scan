import { Component, computed, input } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { CanvasNode } from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import { NodeStatusUpdate } from '@core/models/node-status.model';
import { NodeCardComponent } from '@core/models/node-plugin.model';

interface InjectionBadge {
  text: string;
  cssClass: string;
}

@Component({
  selector: 'app-pcd-injection-card',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './pcd-injection-card.component.html',
  styleUrl: './pcd-injection-card.component.css',
})
export class PcdInjectionCardComponent implements NodeCardComponent {
  node = input.required<CanvasNode>();
  status = input<NodeStatusUpdate | null>(null);

  protected badge = computed<InjectionBadge | null>(() => {
    const s = this.status();
    if (!s) return null;

    const appValue = String(s.application_state?.value ?? '');

    switch (appValue) {
      case 'ready':
        return { text: '● READY', cssClass: 'text-syn-color-success-600' };
      case 'waiting':
        return { text: '○ WAITING', cssClass: 'text-syn-color-neutral-400' };
      case 'error':
        return { text: '✕ ERROR', cssClass: 'text-syn-color-danger-600' };
      default:
        return null;
    }
  });

  protected endpoint = computed(() => {
    const nodeId = this.node().data.id;
    return `/api/v1/pcd-injection/${nodeId}/upload`;
  });
}
