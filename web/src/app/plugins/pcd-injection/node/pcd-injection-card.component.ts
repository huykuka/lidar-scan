import {Component, computed, input} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CanvasNode} from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import {NodeStatusUpdate} from '@core/models/node-status.model';
import {NodeCardComponent} from '@core/models/node-plugin.model';

/**
 * Canvas card component for PCD Injection Nodes.
 * Displays the injection status as a compact badge.
 */
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

  /**
   * Human-readable status label shown on the canvas card.
   */
  protected statusLabel = computed(() => {
    const s = this.status();
    if (!s) return 'Idle';
    const appValue = String(s.application_state?.value ?? '');
    switch (appValue) {
      case 'ready':
        return 'Receiving';
      case 'waiting':
        return 'Waiting';
      case 'error':
        return 'Error';
      default:
        return 'Idle';
    }
  });

  protected statusVariant = computed(() => {
    const s = this.status();
    const appValue = String(s?.application_state?.value ?? '');
    switch (appValue) {
      case 'ready':
        return 'success' as const;
      case 'error':
        return 'danger' as const;
      default:
        return 'neutral' as const;
    }
  });
}
