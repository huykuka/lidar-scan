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

    // Check connection status for real hardware sensors
    const lidarStatus = status as LidarNodeStatus;
    if (lidarStatus.connection_status) {
      if (lidarStatus.connection_status === 'disconnected') {
        return { variant: 'danger', label: 'Disconnected' };
      }
      if (lidarStatus.connection_status === 'error') {
        return { variant: 'danger', label: 'Error' };
      }
      if (lidarStatus.connection_status === 'starting') {
        return { variant: 'warning', label: 'Starting' };
      }
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

  // Additional data extraction methods for sensor nodes
  getNodeMode(): string {
    return (this.node().data as any).mode || 'N/A';
  }

  getNodePipelineName(): string {
    const pipeline = (this.node().data as any).pipeline_name;
    return pipeline && pipeline !== 'none' ? pipeline : 'None';
  }

  getNodePcdPath(): string | null {
    return (this.node().data as any).pcd_path || null;
  }

  getNodePose(): { x: number; y: number; z: number } | null {
    const pose = (this.node().data as any).pose;
    if (pose) {
      return {
        x: pose.x || 0,
        y: pose.y || 0,
        z: pose.z || 0,
      };
    }
    return null;
  }

  getNodeImuUdpPort(): number | null {
    const args = (this.node().data as any).launch_args || '';
    const imuPortMatch = args.match(/imu_udp_port:=(\d+)/);
    return imuPortMatch ? parseInt(imuPortMatch[1]) : null;
  }

  getNodeHostname(): string | null {
    const args = (this.node().data as any).launch_args || '';
    const hostMatch = args.match(/hostname:=([\d\.]+)/);
    return hostMatch ? hostMatch[1] : null;
  }

  getFrameAge(): string | null {
    const status = this.status();
    if (!status) {
      return null;
    }

    // Handle both lidar and fusion nodes
    let age: number | null = null;
    if ('frame_age_seconds' in status) {
      age = (status as LidarNodeStatus).frame_age_seconds;
    } else if ('broadcast_age_seconds' in status) {
      age = (status as FusionNodeStatus).broadcast_age_seconds;
    }

    if (age === null) {
      return null;
    }

    if (age < 1) {
      return '<1s';
    } else if (age < 60) {
      return `${Math.floor(age)}s`;
    } else {
      return `${Math.floor(age / 60)}m`;
    }
  }

  isFrameStale(): boolean {
    const status = this.status();
    if (!status) {
      return false;
    }

    // Handle both lidar and fusion nodes
    let age: number | null = null;
    if ('frame_age_seconds' in status) {
      age = (status as LidarNodeStatus).frame_age_seconds;
    } else if ('broadcast_age_seconds' in status) {
      age = (status as FusionNodeStatus).broadcast_age_seconds;
    }

    if (age === null) {
      return false;
    }

    return age > 5 && age <= 60; // Consider stale between 5-60 seconds
  }

  isFrameVeryStale(): boolean {
    const status = this.status();
    if (!status) {
      return false;
    }

    // Handle both lidar and fusion nodes
    let age: number | null = null;
    if ('frame_age_seconds' in status) {
      age = (status as LidarNodeStatus).frame_age_seconds;
    } else if ('broadcast_age_seconds' in status) {
      age = (status as FusionNodeStatus).broadcast_age_seconds;
    }

    if (age === null) {
      return false;
    }

    return age > 60; // Consider very stale after 1 minute
  }
}
