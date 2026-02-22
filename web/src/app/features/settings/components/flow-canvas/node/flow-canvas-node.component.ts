import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarConfig } from '../../../../../core/models/lidar.model';
import { FusionConfig } from '../../../../../core/models/fusion.model';
import { LidarNodeStatus, FusionNodeStatus } from '../../../../../core/services/api/nodes-api.service';

export interface CanvasNode {
  id: string;
  type: 'sensor' | 'fusion';
  data: LidarConfig | FusionConfig;
  position: { x: number; y: number };
}

@Component({
  selector: 'app-flow-canvas-node',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './flow-canvas-node.component.html',
  styleUrl: './flow-canvas-node.component.css',
})
export class FlowCanvasNodeComponent {
  node = input.required<CanvasNode>();
  status = input<LidarNodeStatus | FusionNodeStatus | null>(null);
  isLoading = input<boolean>(false);
  isDragging = input<boolean>(false);

  onEdit = output<void>();
  onDelete = output<void>();
  onToggleEnabled = output<boolean>();

  statusBadge(): {
    variant: 'primary' | 'success' | 'neutral' | 'warning' | 'danger';
    label: string;
  } {
    const status = this.status();
    const enabled = (this.node().data as any).enabled;

    if (!enabled) {
      return { variant: 'neutral', label: 'Disabled' };
    }

    if (!status) {
      return { variant: 'warning', label: 'Unknown' };
    }

    if (status.last_error) {
      return { variant: 'danger', label: 'Error' };
    }

    if (status.running) {
      return { variant: 'success', label: 'Running' };
    }

    if (enabled && !status.running) {
      return { variant: 'warning', label: 'Starting' };
    }

    return { variant: 'neutral', label: 'Stopped' };
  }

  getNodeName(): string {
    return (this.node().data as any).name || this.node().id;
  }

  getNodeDriver(): string {
    return (this.node().data as any).driver || 'N/A';
  }

  getNodeTopicPrefix(): string {
    return (this.node().data as any).topic_prefix || 'N/A';
  }

  getNodeSensorCount(): number {
    return (this.node().data as any).sensor_ids?.length || 0;
  }

  getNodePipeline(): string {
    return (this.node().data as any).pipeline || 'default';
  }

  isNodeEnabled(): boolean {
    return (this.node().data as any).enabled || false;
  }
}
