import { Component, computed, inject, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarConfig } from '../../../../core/models/lidar.model';
import { NodesStatusResponse } from '../../../../core/services/api/nodes-api.service';
import { RecordingStoreService } from '../../../../core/services/stores/recording-store.service';
import { RecordingApiService } from '../../../../core/services/api/recording-api.service';

@Component({
  selector: 'app-lidar-card',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './lidar-card.component.html',
})
export class LidarCardComponent {
  private recordingStore = inject(RecordingStoreService);
  private recordingApi = inject(RecordingApiService);

  // Inputs
  lidar = input.required<LidarConfig>();
  isLoading = input<boolean>(false);
  nodeStatus = input<NodesStatusResponse['lidars'][0] | null>(null);

  // Outputs
  toggleEnabled = output<{ lidar: LidarConfig; enabled: boolean }>();
  edit = output<LidarConfig>();
  delete = output<string>();
  
  // Recording state
  protected isRecording = computed(() => {
    const topic = this.getTopic();
    const checkFn = this.recordingStore.isRecording();
    return checkFn(topic);
  });
  
  protected activeRecording = computed(() => {
    const topic = this.getTopic();
    const getFn = this.recordingStore.getActiveRecordingByTopic();
    return getFn(topic);
  });
  
  protected recordingDuration = signal<number>(0);
  private recordingInterval: any = null;

  protected getTopic(): string {
    const l = this.lidar();
    return l.processed_topic || l.raw_topic || (l.topic_prefix ? `${l.topic_prefix}_raw_points` : '');
  }
  
  protected async toggleRecording(): Promise<void> {
    const topic = this.getTopic();
    const lidar = this.lidar();
    
    if (this.isRecording()) {
      // Stop recording
      const recording = this.activeRecording();
      if (recording) {
        try {
          await this.recordingApi.stopRecording(recording.recording_id).toPromise();
          await this.recordingStore.loadRecordings();
          this.stopRecordingTimer();
        } catch (error) {
          console.error('Failed to stop recording:', error);
        }
      }
    } else {
      // Start recording
      try {
        await this.recordingApi.startRecording({
          topic,
          name: `${lidar.name} Recording`,
          metadata: {
            sensor_id: lidar.id,
            sensor_name: lidar.name,
            mode: lidar.mode,
            pipeline: lidar.pipeline_name,
            pose: lidar.pose
          }
        }).toPromise();
        await this.recordingStore.loadRecordings();
        this.startRecordingTimer();
      } catch (error) {
        console.error('Failed to start recording:', error);
      }
    }
  }
  
  private startRecordingTimer(): void {
    this.recordingDuration.set(0);
    this.recordingInterval = setInterval(() => {
      this.recordingDuration.update(d => d + 1);
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
