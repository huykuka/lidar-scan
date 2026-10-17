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
import {RecordingRowComponent} from './components/recording-row/recording-row.component';
import {AuthService} from '@core/services/auth.service';
import {ToastService} from '@core/services/toast.service';
import {BlobStorageService} from '@core/services/blob-storage.service';
import {DialogService} from '@core/services/dialog.service';
import {debounceTime, distinctUntilChanged, firstValueFrom, interval, Subject, Subscription} from 'rxjs';
import { UntilDestroy, untilDestroyed } from '@ngneat/until-destroy';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';

const POLL_INTERVAL_MS = 3000;

@UntilDestroy()
@Component({
  selector: 'app-recordings',
  imports: [SynergyComponentsModule, RecordingRowComponent, UploadProgressPanelComponent],
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
  // Filtering, sorting and paging happen on the server; these are the rows of the current page.
  protected filteredRecordings = computed(() => this.recordings());
  protected sortedRecordings = this.filteredRecordings;
  protected total = computed(() => this.recordingStore.total());
  protected allFilteredSelected = computed(() => {
    const filtered = this.filteredRecordings();
    const sel = this.selectedRecordingIds();
    return filtered.length > 0 && filtered.every((r: Recording) => sel.has(r.id));
  });
  protected currentPage = signal(1);
  protected pageSize = signal(25);
  protected readonly pageSizeOptions = [10, 25, 50, 100];
  private readonly searchInput$ = new Subject<string>();

  /** True when any recording is still processing — drives poll */
  protected hasProcessing = computed(() =>
    this.recordings().some((r: Recording) => r.status === 'processing'),
  );

  private recordingStore = inject(RecordingStoreService);
  // State
  protected recordings = this.recordingStore.recordings;
  protected isLoading = this.recordingStore.select('isLoading');
  private recordingApi = inject(RecordingApiService);
  private navService = inject(NavigationService);
  private router = inject(Router);
  private dialogService = inject(DialogService);
  private toast = inject(ToastService);
  protected readonly isService = inject(AuthService).isService;
  private blobStorage = inject(BlobStorageService);
  private destroyRef = inject(DestroyRef);

  private pollSub: Subscription | null = null;

  constructor() {
    this.searchInput$
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        this.searchQuery.set(value.trim());
        this.goToPage(1);
      });

    // Start/stop poll reactively based on whether any recording is 'processing'
    effect(() => {
      const processing = this.hasProcessing();
      if (processing && !this.pollSub) {
        this.pollSub = interval(POLL_INTERVAL_MS)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe(() => this.reload());
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
    await this.reload();
  }

  /** Load the current page; if it no longer exists (e.g. after deletes) fall back to the last one. */
  private async reload(): Promise<void> {
    const load = () =>
      this.recordingStore.loadPage({
        q: this.searchQuery() || undefined,
        limit: this.pageSize(),
        offset: (this.currentPage() - 1) * this.pageSize(),
      });
    await load();
    const lastPage = Math.max(1, Math.ceil(this.total() / this.pageSize()));
    if (this.currentPage() > lastPage) {
      this.currentPage.set(lastPage);
      await load();
    }
  }

  protected onSearch(value: string): void {
    this.searchInput$.next(value);
  }

  protected goToPage(page: number): void {
    this.currentPage.set(page);
    this.clearSelection();
    void this.reload();
  }

  protected onPageSizeChange(size: number): void {
    this.pageSize.set(size);
    this.goToPage(1);
  }

  /** Selection only ever covers the visible page, so drop it when the page changes. */
  private clearSelection(): void {
    this.selectedRecordingIds.set(new Set());
  }

  protected async refreshRecordings(): Promise<void> {
    await this.reload();
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

  protected blobUploadingIds = signal<Set<string>>(new Set());

  protected async uploadToBlob(recording: Recording): Promise<void> {
    this.blobUploadingIds.update((s) => new Set(s).add(recording.id));
    try {
      await firstValueFrom(this.recordingApi.uploadToBlobStorage(recording.id));
      this.toast.neutral(`Uploading ${recording.name} in the background…`);
      // Optimistic: the server pushes the final state (uploaded / failed) over the WebSocket
      this.recordingStore.applyBlobUpload(recording.id, {
        status: 'queued',
        started_at: new Date().toISOString(),
      });
    } catch (err: any) {
      this.toast.danger(err?.error?.detail ?? 'Could not start upload');
      void this.blobStorage.refresh(); // credentials may have gone stale
    } finally {
      this.blobUploadingIds.update((s) => {
        const next = new Set(s);
        next.delete(recording.id);
        return next;
      });
    }
  }

  protected async cancelBlobUpload(recording: Recording): Promise<void> {
    try {
      await firstValueFrom(this.recordingApi.cancelBlobUpload(recording.id));
      this.recordingStore.applyBlobUpload(recording.id, null);
      this.toast.neutral(`Upload of ${recording.name} cancelled`);
    } catch (err: any) {
      // 409 = it already finished/failed; the pushed state will update the card
      this.toast.warning(err?.error?.detail ?? 'Could not cancel upload');
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
      await this.reload();
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
      await this.reload();
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

      await this.reload();
      this.selectedRecordingIds.set(new Set());
      this.isSelectionMode.set(false);
    } catch (error) {
      console.error('Failed to perform bulk deletion:', error);
    } finally {
      this.isDeleting.set(false);
    }
  }

  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    if (this.isSelectionMode()) this.toggleSelectionMode();
  }

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
