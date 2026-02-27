import { Component, computed, inject, input, output, signal, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeConfig, NodeStatus } from '../../../../core/models/node.model';
import { NodeStoreService } from '../../../../core/services/stores/node-store.service';
import { RecordingStoreService } from '../../../../core/services/stores/recording-store.service';
import { RecordingApiService } from '../../../../core/services/api/recording-api.service';
import { CalibrationApiService } from '../../../../core/services/api/calibration-api.service';
import {
  CalibrationNodeStatus,
  CalibrationResult,
} from '../../../../core/models/calibration.model';

@Component({
  selector: 'app-node-card',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './node-card.component.html',
})
export class NodeCardComponent implements OnDestroy {
  private nodeStore = inject(NodeStoreService);
  private recordingStore = inject(RecordingStoreService);
  private recordingApi = inject(RecordingApiService);
  private calibrationApi = inject(CalibrationApiService);

  // Inputs
  node = input.required<NodeConfig>();
  isLoading = input<boolean>(false);
  status = input<NodeStatus | null>(null);

  // Outputs
  toggleEnabled = output<{ node: NodeConfig; enabled: boolean }>();
  edit = output<NodeConfig>();
  delete = output<string>();

  // Derived Definition
  definition = computed(() => {
    return this.nodeStore.nodeDefinitions().find((d) => d.type === this.node().type);
  });

  // Category specific checks
  isSensor = computed(() => this.node().category === 'sensor');
  isFusion = computed(() => this.node().category === 'fusion');
  isCalibration = computed(() => {
    const node = this.node();
    const result = node.type === 'calibration';
    console.log('[NodeCard] isCalibration check:', { nodeId: node.id, type: node.type, category: node.category, result });
    return result;
  });

  // Calibration state
  protected calibrationStatus = computed(() => {
    if (!this.isCalibration()) return null;
    return this.status() as CalibrationNodeStatus | null;
  });

  protected hasPendingCalibration = computed(() => {
    return this.calibrationStatus()?.has_pending || false;
  });

  protected pendingResults = computed(() => {
    return this.calibrationStatus()?.pending_results || {};
  });

  protected isCalibrating = signal<boolean>(false);
  protected calibrationError = signal<string | null>(null);

  // Recording state (Sensors only)
  protected isRecording = computed(() => {
    if (!this.isSensor()) return false;
    const checkFn = this.recordingStore.isRecording();
    return checkFn(this.node().id);
  });

  protected activeRecording = computed(() => {
    if (!this.isSensor()) return null;
    const getFn = this.recordingStore.getActiveRecordingByNodeId();
    return getFn(this.node().id);
  });

  protected recordingDuration = signal<number>(0);
  private recordingInterval: any = null;

  protected getTopic(): string {
    const n = this.node();
    const config = n.config || {};
    const s: any = this.status();

    if (this.isSensor()) {
      return (
        s?.raw_topic ||
        config['processed_topic'] ||
        config['raw_topic'] ||
        (config['topic_prefix'] ? `${config['topic_prefix']}_raw_points` : '')
      );
    } else if (this.isFusion()) {
      return s?.topic || config['topic'] || '';
    } else {
      return s?.topic || config['topic'] || '';
    }
  }

  protected async toggleRecording(): Promise<void> {
    if (!this.isSensor()) return;

    const node = this.node();
    const config = node.config || {};

    if (this.isRecording()) {
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
      try {
        // Start timer immediately when user clicks record
        this.startRecordingTimer();

        await this.recordingApi
          .startRecording({
            node_id: node.id,
            name: `${node.name} Recording`,
            metadata: {
              sensor_id: node.id,
              sensor_name: node.name,
              mode: config['mode'],
              pipeline: config['pipeline_name'],
            },
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

  // Calibration Controls
  protected async triggerCalibration(): Promise<void> {
    if (!this.isCalibration()) return;

    this.isCalibrating.set(true);
    this.calibrationError.set(null);

    try {
      await this.calibrationApi.triggerCalibration(this.node().id);
      // Status will update via WebSocket
    } catch (error: any) {
      console.error('Failed to trigger calibration:', error);
      this.calibrationError.set(error?.error?.detail || 'Calibration failed');
    } finally {
      this.isCalibrating.set(false);
    }
  }

  protected async acceptCalibration(): Promise<void> {
    if (!this.isCalibration()) return;

    this.isCalibrating.set(true);
    this.calibrationError.set(null);

    try {
      await this.calibrationApi.acceptCalibration(this.node().id);
      // Reload will happen automatically via backend
    } catch (error: any) {
      console.error('Failed to accept calibration:', error);
      this.calibrationError.set(error?.error?.detail || 'Failed to accept calibration');
    } finally {
      this.isCalibrating.set(false);
    }
  }

  protected async rejectCalibration(): Promise<void> {
    if (!this.isCalibration()) return;

    this.isCalibrating.set(true);

    try {
      await this.calibrationApi.rejectCalibration(this.node().id);
      // Status will update via WebSocket
    } catch (error: any) {
      console.error('Failed to reject calibration:', error);
      this.calibrationError.set(error?.error?.detail || 'Failed to reject calibration');
    } finally {
      this.isCalibrating.set(false);
    }
  }

  protected getQualityBadgeVariant(
    quality: string,
  ): 'success' | 'warning' | 'danger' | 'neutral' {
    switch (quality) {
      case 'excellent':
        return 'success';
      case 'good':
        return 'warning';
      case 'poor':
        return 'danger';
      default:
        return 'neutral';
    }
  }

  protected getQualityIcon(quality: string): string {
    switch (quality) {
      case 'excellent':
        return 'check_circle';
      case 'good':
        return 'warning';
      case 'poor':
        return 'error';
      default:
        return 'help';
    }
  }

  ngOnDestroy(): void {
    this.stopRecordingTimer();
  }
}
