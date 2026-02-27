import { Component, computed, inject, input, output, signal, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarConfig } from '../../../../../core/models/lidar.model';
import { FusionConfig } from '../../../../../core/models/fusion.model';
import {
  NodeConfig,
  LidarNodeStatus,
  FusionNodeStatus,
} from '../../../../../core/models/node.model';
import { RecordingStoreService } from '../../../../../core/services/stores/recording-store.service';
import { RecordingApiService } from '../../../../../core/services/api/recording-api.service';

export interface CanvasNode {
  id: string;
  type: 'sensor' | 'fusion' | 'operation';
  data: NodeConfig;
  position: { x: number; y: number };
}

@Component({
  selector: 'app-flow-canvas-node',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './flow-canvas-node.component.html',
  styleUrl: './flow-canvas-node.component.css',
})
export class FlowCanvasNodeComponent implements OnDestroy {
  private recordingStore = inject(RecordingStoreService);
  private recordingApi = inject(RecordingApiService);

  node = input.required<CanvasNode>();
  status = input<LidarNodeStatus | FusionNodeStatus | null>(null);
  isLoading = input<boolean>(false);
  isDragging = input<boolean>(false);

  onEdit = output<void>();
  onDelete = output<void>();
  onToggleEnabled = output<boolean>();

  /** Fired when user starts dragging from a port. */
  portDragStart = output<{ nodeId: string; portType: 'input' | 'output'; event: MouseEvent }>();
  /** Fired when user releases on a port (potential drop target). */
  portDrop = output<{ nodeId: string; portType: 'input' | 'output' }>();

  // Recording state
  protected isRecording = computed(() => {
    const checkFn = this.recordingStore.isRecording();
    return checkFn(this.node().id);
  });

  protected activeRecording = computed(() => {
    const getFn = this.recordingStore.getActiveRecordingByNodeId();
    return getFn(this.node().id);
  });

  protected recordingDuration = signal<number>(0);
  private recordingInterval: any = null;

  // UI state
  isExpanded = signal<boolean>(false);

  statusBadge(): {
    variant: 'primary' | 'success' | 'neutral' | 'warning' | 'danger';
    label: string;
  } {
    const status = this.status();
    const enabled = this.node().data.enabled;

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
    return this.node().data.name || this.node().id;
  }

  getNodeDriver(): string {
    return (this.node().data.config as any).driver || 'N/A';
  }

  isNodeEnabled(): boolean {
    return this.node().data.enabled || false;
  }

  getNodeIcon(): string {
    if (this.node().type === 'sensor') return 'sensors';
    if (this.node().type === 'fusion') return 'hub';

    // Operation specific icons
    const opType = (this.node().data.config as any).op_type;
    if (opType === 'crop') return 'crop';
    if (opType === 'downsample') return 'grid_view';
    if (opType === 'outlier_removal') return 'auto_fix_normal';

    return 'settings_input_component';
  }

  getConfigProperties(): {
    label: string;
    value: string;
    isBadge?: boolean;
    badgeVariant?: 'primary' | 'success' | 'neutral' | 'warning' | 'danger';
  }[] {
    const dataConfig = this.node().data.config as any;
    const config = dataConfig.op_config ? { ...dataConfig.op_config } : { ...dataConfig };

    // Remove metadata/internal fields from display
    delete config.op_type;
    delete config.topic;
    delete config.sensor_ids;

    if (this.node().type === 'operation' && dataConfig.op_type) {
      config['algorithm'] = dataConfig.op_type;
    }

    const params: {
      label: string;
      value: string;
      isBadge?: boolean;
      badgeVariant?: 'primary' | 'success' | 'neutral' | 'warning' | 'danger';
    }[] = [];

    const processValue = (key: string, val: any) => {
      if (val === undefined || val === null || val === '') return;

      if (typeof val === 'object' && !Array.isArray(val)) {
        // Recursively unpack nested objects without hardcoding
        Object.entries(val).forEach(([subKey, subVal]) => {
          processValue(`${key}_${subKey}`, subVal);
        });
        return;
      }

      let displayVal = '';
      if (Array.isArray(val)) {
        displayVal = `[${val.map((v) => (typeof v === 'number' ? v.toFixed(1) : v)).join(',')}]`;
      } else if (typeof val === 'number') {
        if (key.toLowerCase().includes('port') || Number.isInteger(val)) {
          displayVal = val.toString();
        } else {
          displayVal = val.toFixed(2);
        }
      } else {
        displayVal = String(val);
      }

      // Special string formatting
      if (key === 'pcd_path') {
        displayVal = displayVal.split('/').pop() || displayVal;
      }
      if (key === 'pipeline_name' && displayVal === 'none') return;

      let label = key.replace(/_/g, ' ');
      label = label.charAt(0).toUpperCase() + label.slice(1);

      let isBadge = false;
      let badgeVariant: 'primary' | 'success' | 'neutral' | 'warning' | 'danger' = 'primary';

      if (key === 'mode') {
        isBadge = true;
        badgeVariant = val === 'real' ? 'primary' : 'neutral';
        displayVal = val === 'real' ? 'Hardware' : 'Simulation';
      }

      params.push({ label, value: displayVal, isBadge, badgeVariant });
    };

    Object.entries(config).forEach(([key, val]) => {
      processValue(key, val);
    });

    return params.slice(0, 20); // Show up to 20 params dynamically
  }

  getFrameAge(): string | null {
    const status = this.status();
    if (!status) {
      return null;
    }

    // Handle both lidar and fusion nodes
    let age: number | null = null;
    if ('frame_age_seconds' in status) {
      age = (status as LidarNodeStatus).frame_age_seconds ?? null;
    } else if ('broadcast_age_seconds' in status) {
      age = (status as FusionNodeStatus).broadcast_age_seconds ?? null;
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
      age = (status as LidarNodeStatus).frame_age_seconds ?? null;
    } else if ('broadcast_age_seconds' in status) {
      age = (status as FusionNodeStatus).broadcast_age_seconds ?? null;
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
      age = (status as LidarNodeStatus).frame_age_seconds ?? null;
    } else if ('broadcast_age_seconds' in status) {
      age = (status as FusionNodeStatus).broadcast_age_seconds ?? null;
    }

    if (age === null) {
      return false;
    }

    return age > 60; // Consider very stale after 1 minute
  }

  // Recording functionality
  protected async toggleRecording(): Promise<void> {
    const data = this.node().data;
    const config = data.config as any;

    if (this.isRecording()) {
      // Stop recording
      const recording = this.activeRecording();
      if (recording) {
        // Stop timer immediately when user clicks stop
        this.stopRecordingTimer();
        
        try {
          await this.recordingApi.stopRecording(recording.recording_id).toPromise();
          await this.recordingStore.loadRecordings();
        } catch (error) {
          console.error('Failed to stop recording:', error);
        }
      }
    } else {
      // Start recording
      try {
        const metadata: any = {
          node_name: data.name,
          node_type: this.node().type,
          node_id: data.id,
        };

        if (this.node().type === 'sensor') {
          metadata.sensor_id = data.id;
          metadata.mode = config.mode;
          metadata.pipeline = config.pipeline_name;
          metadata.pose = config.pose;
        } else if (this.node().type === 'fusion') {
          metadata.fusion_id = data.id;
          metadata.sensor_ids = config.sensor_ids;
          metadata.pipeline = config.pipeline;
        }

        // Start timer immediately when user clicks record
        this.startRecordingTimer();

        await this.recordingApi
          .startRecording({
            node_id: data.id,
            name: `${data.name} Recording`,
            metadata,
          })
          .toPromise();
        await this.recordingStore.loadRecordings();
      } catch (error) {
        console.error('Failed to start recording:', error);
        // Stop timer if recording failed to start
        this.stopRecordingTimer();
      }
    }
  }

  private startRecordingTimer(): void {
    this.recordingDuration.set(0);
    this.recordingInterval = setInterval(() => {
      this.recordingDuration.update((d) => d + 1);
    }, 1000);
  }

  private stopRecordingTimer(): void {
    if (this.recordingInterval) {
      clearInterval(this.recordingInterval);
      this.recordingInterval = null;
    }
    this.recordingDuration.set(0);
  }

  protected formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  ngOnDestroy(): void {
    this.stopRecordingTimer();
  }
}
