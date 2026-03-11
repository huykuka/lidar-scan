import { Component, computed, inject, input, OnDestroy, signal } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { CanvasNode } from '../flow-canvas-node.component';
import { RecordingStoreService } from '../../../../../../core/services/stores/recording-store.service';
import { RecordingApiService } from '../../../../../../core/services/api/recording-api.service';

@Component({
  selector: 'app-node-recording-controls',
  imports: [SynergyComponentsModule],
  templateUrl: './node-recording-controls.html',
})
export class NodeRecordingControls implements OnDestroy {
  private recordingStore = inject(RecordingStoreService);
  private recordingApi = inject(RecordingApiService);

  node = input.required<CanvasNode>();

  protected isRecording = computed(() => {
    const checkFn = this.recordingStore.isRecording();
    return checkFn(this.node().id);
  });

  protected activeRecording = computed(() => {
    const getFn = this.recordingStore.getActiveRecordingByNodeId();
    return getFn(this.node().id);
  });

  protected recordingDuration = signal<number>(0);
  private recordingInterval: ReturnType<typeof setInterval> | null = null;

  protected async toggleRecording(): Promise<void> {
    const data = this.node().data;
    const config = data.config as any;

    if (this.isRecording()) {
      const recording = this.activeRecording();
      if (recording) {
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
        const metadata: any = {
          node_name: data.name,
          node_type: data.type || data.category,
          node_id: data.id,
        };

        if (config.mode !== undefined || config.pose !== undefined) {
          metadata.sensor_id = data.id;
          metadata.mode = config.mode;
          metadata.pipeline_name = config.pipeline_name;
          metadata.pose = config.pose;
        }

        if (Array.isArray(config.sensor_ids)) {
          metadata.fusion_id = data.id;
          metadata.sensor_ids = config.sensor_ids;
          metadata.pipeline_name = config.pipeline_name;
        }

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
