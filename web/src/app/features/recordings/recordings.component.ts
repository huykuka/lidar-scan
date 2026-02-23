import { Component, computed, effect, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { RecordingStoreService } from '../../core/services/stores/recording-store.service';
import { RecordingApiService } from '../../core/services/api/recording-api.service';
import { NavigationService } from '../../core/services/navigation.service';
import { DialogService } from '../../core/services/dialog.service';
import { Recording } from '../../core/models/recording.model';
import { RecordingViewerComponent } from './components/recording-viewer/recording-viewer.component';

@Component({
  selector: 'app-recordings',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './recordings.component.html',
  styleUrl: './recordings.component.css',
})
export class RecordingsComponent implements OnInit {
  private recordingStore = inject(RecordingStoreService);
  private recordingApi = inject(RecordingApiService);
  private navService = inject(NavigationService);
  private dialogService = inject(DialogService);

  // State
  protected recordings = this.recordingStore.recordings;
  protected isLoading = this.recordingStore.select('isLoading');
  protected searchQuery = signal<string>('');
  protected selectedRecording = signal<Recording | null>(null);
  protected showDeleteDialog = signal<boolean>(false);
  protected recordingToDelete = signal<Recording | null>(null);
  protected isDeleting = signal<boolean>(false);

  // Computed
  protected filteredRecordings = computed(() => {
    const query = this.searchQuery().toLowerCase();
    const recs = this.recordings();
    if (!query || !recs) return recs || [];

    return recs.filter(
      (r: Recording) =>
        r.name.toLowerCase().includes(query) ||
        r.topic.toLowerCase().includes(query) ||
        (r.metadata?.sensor_name && r.metadata.sensor_name.toLowerCase().includes(query)),
    );
  });

  protected sortedRecordings = computed(() => {
    return [...this.filteredRecordings()].sort((a, b) => {
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  });

  async ngOnInit() {
    this.navService.setPageConfig({
      title: 'Recordings',
      subtitle: 'Browse and manage your LiDAR recording files',
    });
    await this.recordingStore.loadRecordings();
  }

  protected async refreshRecordings(): Promise<void> {
    await this.recordingStore.loadRecordings();
  }

  protected formatDate(dateStr: string): string {
    const date = new Date(dateStr);
    return date.toLocaleString();
  }

  protected formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  protected formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  }

  protected async loadForPlayback(recording: Recording): Promise<void> {
    // Open viewer using DialogService
    this.dialogService.open(
      RecordingViewerComponent,
      {
        label: `Recording Viewer - ${recording.name}`,
        class: 'recording-viewer-dialog',
      },
      {
        recordingId: recording.id,
        recordingName: recording.name,
      },
    );
  }

  protected downloadRecording(recording: Recording): void {
    // Download the recording file
    const filename = `${recording.name}_${recording.created_at.substring(0, 10)}.lidr`;
    this.recordingApi.downloadRecording(recording.id, filename);
  }

  protected confirmDelete(recording: Recording): void {
    this.recordingToDelete.set(recording);
    this.showDeleteDialog.set(true);
  }

  protected cancelDelete(): void {
    this.recordingToDelete.set(null);
    this.showDeleteDialog.set(false);
  }

  protected async deleteRecording(): Promise<void> {
    const recording = this.recordingToDelete();
    if (!recording) return;

    this.isDeleting.set(true);
    try {
      await this.recordingApi.deleteRecording(recording.id).toPromise();
      await this.recordingStore.loadRecordings();
      this.showDeleteDialog.set(false);
      this.recordingToDelete.set(null);
    } catch (error) {
      console.error('Failed to delete recording:', error);
    } finally {
      this.isDeleting.set(false);
    }
  }

  protected selectRecording(recording: Recording): void {
    this.selectedRecording.set(recording);
  }

  protected closeDetails(): void {
    this.selectedRecording.set(null);
  }

  protected onThumbnailError(event: Event): void {
    // Hide broken image on error
    const img = event.target as HTMLImageElement;
    img.style.display = 'none';
  }
}
