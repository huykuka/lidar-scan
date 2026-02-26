import { Component, computed, inject, input, output, signal, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeConfig, NodeStatus } from '../../../../core/models/node.model';
import { NodeStoreService } from '../../../../core/services/stores/node-store.service';
import { RecordingStoreService } from '../../../../core/services/stores/recording-store.service';
import { RecordingApiService } from '../../../../core/services/api/recording-api.service';

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

  ngOnDestroy(): void {
    this.stopRecordingTimer();
  }
}
