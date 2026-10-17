import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  ElementRef,
  effect,
  HostListener,
  inject,
  OnInit,
  signal,
  viewChild
} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {RecordingStoreService} from '@core/services/stores/recording-store.service';
import {RecordingApiService} from '@core/services/api/recording-api.service';
import {NavigationService} from '@core/services';
import {Router} from '@angular/router';
import {Recording} from '@core/models';
import {UploadProgressPanelComponent} from './components/upload-progress-panel/upload-progress-panel.component';
import {RecordingUploadService} from '@core/services/recording-upload.service';
import {RecordingCardComponent} from './components/recording-card/recording-card.component';
import {DialogService} from '@core/services/dialog.service';
import {firstValueFrom, interval, Subscription} from 'rxjs';
import { UntilDestroy, untilDestroyed } from '@ngneat/until-destroy';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';

const POLL_INTERVAL_MS = 3000;

@UntilDestroy()
@Component({
  selector: 'app-recordings',
  imports: [SynergyComponentsModule, RecordingCardComponent, UploadProgressPanelComponent],
  templateUrl: './recordings.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './recordings.component.css',
})
export class RecordingsComponent implements OnInit {
  private readonly fileInputRef = viewChild.required<ElementRef<HTMLInputElement>>('fileInput');

  protected searchQuery = signal<string>('');
  protected selectedRecording = signal<Recording | null>(null);
  protected isDeleting = signal<boolean>(false);
  private readonly uploader = inject(RecordingUploadService);
  // Selection state
  protected isSelectionMode = signal<boolean>(false);
  protected selectedRecordingIds = signal<Set<string>>(new Set());
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
  protected allFilteredSelected = computed(() => {
    const filtered = this.filteredRecordings();
    const sel = this.selectedRecordingIds();
    return filtered.length > 0 && filtered.every((r: Recording) => sel.has(r.id));
  });
  protected sortedRecordings = computed(() => {
    return [...this.filteredRecordings()].sort((a, b) => {
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  });

  /** True when any recording is still processing — drives poll */
  protected hasProcessing = computed(() =>
    this.recordings().some((r: Recording) => r.status === 'processing')
  );

  private recordingStore = inject(RecordingStoreService);
  // State
  protected recordings = this.recordingStore.recordings;
  protected isLoading = this.recordingStore.select('isLoading');
  private recordingApi = inject(RecordingApiService);
  private navService = inject(NavigationService);
  private router = inject(Router);
  private dialogService = inject(DialogService);
  private destroyRef = inject(DestroyRef);

  private pollSub: Subscription | null = null;
  private host = inject<ElementRef<HTMLElement>>(ElementRef);

  constructor() {
    // Capture phase so the click ending a drag is swallowed before the cards see it
    this.host.nativeElement.addEventListener('click', this.onGridClickCapture, true);
    this.destroyRef.onDestroy(() => this.host.nativeElement.removeEventListener('click', this.onGridClickCapture, true));
    // Start/stop poll reactively based on whether any recording is 'processing'
    effect(() => {
      const processing = this.hasProcessing();
      if (processing && !this.pollSub) {
        this.pollSub = interval(POLL_INTERVAL_MS)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe(() => this.recordingStore.loadRecordings());
      } else if (!processing && this.pollSub) {
        this.pollSub.unsubscribe();
        this.pollSub = null;
      }
    });
  }

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

  /** Download every selected recording, staggered so the browser doesn't drop the extra downloads. */
  protected async downloadSelected(): Promise<void> {
    const selected = this.recordings().filter((r: Recording) => this.selectedRecordingIds().has(r.id));
    for (const [i, recording] of selected.entries()) {
      if (i > 0) await new Promise((resolve) => setTimeout(resolve, 500));
      this.downloadRecording(recording);
    }
  }

  protected async renameRecording({
    recording,
    name,
  }: {
    recording: Recording;
    name: string;
  }): Promise<void> {
    try {
      await firstValueFrom(this.recordingApi.renameRecording(recording.id, name));
      await this.recordingStore.loadRecordings();
    } catch (error) {
      console.error('Failed to rename recording:', error);
    }
  }

  protected async confirmDelete(recording: Recording): Promise<void> {
    const confirmed = await this.dialogService.confirm({
      title: 'Delete Recording',
      message: `Are you sure you want to delete ${recording.name}? This action cannot be undone.`,
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });

    if (!confirmed) return;

    this.isDeleting.set(true);
    try {
      await firstValueFrom(this.recordingStore.deleteRecording(recording.id));
      await this.recordingStore.loadRecordings();
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

  protected async confirmBulkDelete(): Promise<void> {
    if (this.selectedRecordingIds().size === 0) return;

    const count = this.selectedRecordingIds().size;
    const confirmed = await this.dialogService.confirm({
      title: 'Delete Multiple Recordings',
      message: `Are you sure you want to delete ${count} recordings? This action cannot be undone.`,
      confirmLabel: 'Delete All',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });

    if (!confirmed) return;

    const ids = Array.from(this.selectedRecordingIds());
    this.isDeleting.set(true);
    try {
      // A more robust implementation might send an array to a bulk delete endpoint.
      // Since recordingApi.deleteRecording takes a single ID, we loop.
      await Promise.all(ids.map((id) => this.recordingApi.deleteRecording(id).toPromise()));

      await this.recordingStore.loadRecordings();
      this.selectedRecordingIds.set(new Set());
      this.isSelectionMode.set(false);
    } catch (error) {
      console.error('Failed to perform bulk deletion:', error);
    } finally {
      this.isDeleting.set(false);
    }
  }

  // --- Drag marquee selection (press and drag over cards to select them) ---

  protected marquee = signal<{x: number; y: number; w: number; h: number} | null>(null);
  private marqueeStart: {x: number; y: number} | null = null;
  private marqueeBase = new Set<string>();
  private marqueeActive = false;
  private suppressNextClick = false;

  protected onGridMouseDown(event: MouseEvent): void {
    if (event.button !== 0) return;
    // Let buttons, inputs and other controls behave normally
    const target = event.target as HTMLElement;
    if (target.closest('button, a, input, textarea, syn-button, syn-icon-button, syn-input, syn-checkbox')) return;
    this.marqueeStart = {x: event.clientX, y: event.clientY};
    this.marqueeBase = event.ctrlKey || event.metaKey || event.shiftKey ? new Set(this.selectedRecordingIds()) : new Set();
    this.marqueeActive = false;
  }

  protected onGridMouseMove(event: MouseEvent): void {
    const start = this.marqueeStart;
    if (!start) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (!this.marqueeActive) {
      if (Math.hypot(dx, dy) < 6) return; // below threshold: still a click
      this.marqueeActive = true;
      this.isSelectionMode.set(true);
    }
    event.preventDefault();
    const x = Math.min(start.x, event.clientX);
    const y = Math.min(start.y, event.clientY);
    const w = Math.abs(dx);
    const h = Math.abs(dy);
    this.marquee.set({x, y, w, h});

    const next = new Set(this.marqueeBase);
    document.querySelectorAll<HTMLElement>('app-recording-card[data-rec-id]').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.right >= x && r.left <= x + w && r.bottom >= y && r.top <= y + h) {
        next.add(el.dataset['recId']!);
      }
    });
    this.selectedRecordingIds.set(next);
  }

  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    if (this.isSelectionMode()) this.toggleSelectionMode();
  }

  @HostListener('document:mouseup')
  protected onGridMouseUp(): void {
    if (!this.marqueeStart) return;
    this.suppressNextClick = this.marqueeActive;
    this.marqueeStart = null;
    this.marqueeActive = false;
    this.marquee.set(null);
  }

  /** Swallow the click that follows a drag so cards don't toggle/open. */
  private onGridClickCapture = (event: MouseEvent): void => {
    if (this.suppressNextClick) {
      event.stopPropagation();
      event.preventDefault();
      this.suppressNextClick = false;
    }
  };

  // --- Upload Methods ---

  protected triggerUpload(): void {
    const input = this.fileInputRef().nativeElement;

    input.value = '';
    input.accept = '.mcap'; // restrict file picker
    input.click();
  }

  protected onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    if (!files.length) return;
    this.uploader.enqueue(files);
    input.value = '';
  }
}
