import { Component, computed, effect, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { RecordingStoreService } from '../../core/services/stores/recording-store.service';
import { RecordingApiService } from '../../core/services/api/recording-api.service';
import { NavigationService } from '../../core/services/navigation.service';
import { Router } from '@angular/router';
import { Recording } from '../../core/models/recording.model';
import { RecordingCardComponent } from './components/recording-card/recording-card.component';

@Component({
  selector: 'app-recordings',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule, RecordingCardComponent],
  templateUrl: './recordings.component.html',
  styleUrl: './recordings.component.css',
})
export class RecordingsComponent implements OnInit {
  private recordingStore = inject(RecordingStoreService);
  private recordingApi = inject(RecordingApiService);
  private navService = inject(NavigationService);
  private router = inject(Router);

  // State
  protected recordings = this.recordingStore.recordings;
  protected isLoading = this.recordingStore.select('isLoading');
  protected searchQuery = signal<string>('');
  protected selectedRecording = signal<Recording | null>(null);
  protected showDeleteDialog = signal<boolean>(false);
  protected recordingToDelete = signal<Recording | null>(null);
  protected isDeleting = signal<boolean>(false);

  // Selection state
  protected isSelectionMode = signal<boolean>(false);
  protected selectedRecordingIds = signal<Set<string>>(new Set());
  protected showBulkDeleteDialog = signal<boolean>(false);

  constructor() {}

  // Computed
  protected filteredRecordings = computed(() => {
    const query = this.searchQuery().toLowerCase();
    const recs = this.recordings();
    if (!query || !recs) return recs || [];

    return recs.filter(
      (r: Recording) =>
        r.name.toLowerCase().includes(query) ||
        r.node_id.toLowerCase().includes(query) ||
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

  protected async loadForPlayback(recording: Recording): Promise<void> {
    this.router.navigate(['/recordings', recording.id]);
  }

  protected downloadRecording(recording: Recording): void {
    // Download the recording file
    const filename = `${recording.name}_${recording.created_at.substring(0, 10)}.zip`;
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
    if (this.isSelectionMode()) {
      this.toggleRecordingSelection(recording.id, !this.selectedRecordingIds().has(recording.id));
      return;
    }
    this.selectedRecording.set(recording);
  }

  protected closeDetails(): void {
    this.selectedRecording.set(null);
  }

  // --- Bulk Selection & Deletion Methods ---

  protected toggleSelectionMode(): void {
    if (this.isSelectionMode()) {
      this.isSelectionMode.set(false);
      this.selectedRecordingIds.set(new Set());
    } else {
      this.isSelectionMode.set(true);
    }
  }

  protected toggleRecordingSelection(id: string, selected: boolean): void {
    const current = new Set(this.selectedRecordingIds());
    if (selected) {
      current.add(id);
    } else {
      current.delete(id);
    }
    this.selectedRecordingIds.set(current);
  }

  protected selectAllFiltered(): void {
    const current = new Set(this.selectedRecordingIds());
    const filtered = this.filteredRecordings();
    const allSelected = filtered.every((r) => current.has(r.id));

    if (allSelected) {
      // Deselect all filtered
      filtered.forEach((r) => current.delete(r.id));
    } else {
      // Select all filtered
      filtered.forEach((r) => current.add(r.id));
    }
    this.selectedRecordingIds.set(new Set(current));
  }

  protected confirmBulkDelete(): void {
    if (this.selectedRecordingIds().size > 0) {
      this.showBulkDeleteDialog.set(true);
    }
  }

  protected cancelBulkDelete(): void {
    this.showBulkDeleteDialog.set(false);
  }

  protected async bulkDeleteRecordings(): Promise<void> {
    const ids = Array.from(this.selectedRecordingIds());
    if (ids.length === 0) return;

    this.isDeleting.set(true);
    try {
      // A more robust implementation might send an array to a bulk delete endpoint.
      // Since recordingApi.deleteRecording takes a single ID, we loop.
      await Promise.all(ids.map((id) => this.recordingApi.deleteRecording(id).toPromise()));

      await this.recordingStore.loadRecordings();
      this.selectedRecordingIds.set(new Set());
      this.isSelectionMode.set(false);
      this.showBulkDeleteDialog.set(false);
    } catch (error) {
      console.error('Failed to perform bulk deletion:', error);
    } finally {
      this.isDeleting.set(false);
    }
  }
}
