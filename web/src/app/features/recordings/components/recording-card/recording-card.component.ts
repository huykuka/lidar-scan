import {Component, Input, signal, input, output} from '@angular/core';
import {DatePipe} from '@angular/common';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {Recording} from '@core/models';
import {environment} from '@env/environment';

@Component({
  selector: 'app-recording-card',
  standalone: true,
  imports: [SynergyComponentsModule, DatePipe],
  templateUrl: './recording-card.component.html',
  styleUrl: './recording-card.component.css',
})
export class RecordingCardComponent {
  @Input({required: true}) recording!: Recording;
  readonly selectable = input(false);
  readonly selected = input(false);
  readonly priority = input(false);

  readonly select = output<Recording>();
  readonly toggleSelection = output<boolean>();
  readonly play = output<Recording>();
  readonly download = output<Recording>();
  readonly delete = output<Recording>();

  // Thumbnail state
  private failedThumbnails = signal<Set<string>>(new Set());
  private loadedThumbnails = signal<Set<string>>(new Set());

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

  protected thumbnailLoadFailed(recordingId: string): boolean {
    return this.failedThumbnails().has(recordingId);
  }

  protected isLoadingThumbnail(recordingId: string): boolean {
    return !this.loadedThumbnails().has(recordingId) && !this.failedThumbnails().has(recordingId);
  }

  protected onThumbnailLoad(recordingId: string): void {
    const loaded = new Set(this.loadedThumbnails());
    loaded.add(recordingId);
    this.loadedThumbnails.set(loaded);
  }

  protected onThumbnailError(recordingId: string): void {
    const failed = new Set(this.failedThumbnails());
    failed.add(recordingId);
    this.failedThumbnails.set(failed);
  }

  protected getThumbnailUrl(recording: Recording): string {
    if (!recording.thumbnail_path) {
      return '';
    }
    // Remove /api/v1 from apiUrl to get base URL (e.g., http://localhost:8004)
    const baseUrl = environment.apiUrl.replace('/api/v1', '');

    // Normalize path: support legacy 'config/' prefix and ensure it starts with / recordigns
    const cleanPath = recording.thumbnail_path.replace(/^config\//, '');

    return `${baseUrl}/${cleanPath}`;
  }
}
