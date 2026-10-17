import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { Recording } from '@core/models';
import { AuthService } from '@core/services/auth.service';
import { BlobStorageService } from '@core/services/blob-storage.service';

@Component({
  // Attribute selector so the component renders as a real <tr> inside the recordings table
  selector: 'tr[app-recording-row]',
  imports: [SynergyComponentsModule, DatePipe],
  templateUrl: './recording-row.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './recording-row.component.css',
  host: {
    '[class.is-selected]': 'selected()',
    '[class.is-selectable]': 'selectable()',
    '(click)': 'select.emit(recording())',
  },
})
export class RecordingRowComponent {
  readonly recording = input.required<Recording>();
  readonly selectable = input(false);
  readonly selected = input(false);

  readonly blobUploading = input(false);

  protected readonly canEdit = inject(AuthService).canEdit;
  /** Service-only, hidden for everyone else. */
  protected readonly isService = inject(AuthService).isService;
  protected readonly blob = inject(BlobStorageService);

  readonly select = output<Recording>();
  readonly toggleSelection = output<boolean>();
  readonly play = output<Recording>();
  readonly download = output<Recording>();
  readonly delete = output<Recording>();
  readonly blobUpload = output<Recording>();
  readonly blobCancel = output<Recording>();
  readonly rename = output<{ recording: Recording; name: string }>();

  /** Derived status helpers — treat missing status as 'ready' */
  protected readonly isProcessing = computed(() => this.recording().status === 'processing');
  protected readonly isFailed = computed(() => this.recording().status === 'failed');
  protected readonly blobState = computed(() => this.recording().metadata?.blob_upload ?? null);
  /** 'uploading' for too long (server restart) is treated as abandoned so it can be retried. */
  protected readonly blobStatus = computed<'idle' | 'queued' | 'uploading' | 'uploaded' | 'failed'>(() => {
    const st = this.blobState();
    if (!st) return 'idle';
    if (st.status === 'queued' || st.status === 'uploading') {
      const started = st.started_at ? Date.parse(st.started_at) : NaN;
      return Number.isFinite(started) && Date.now() - started > (st.timeout_s ?? 7200) * 1000 ? 'failed' : st.status;
    }
    return st.status;
  });
  protected readonly blobProgress = computed(() => Math.round(this.blobState()?.progress ?? 0));
  protected readonly blobProgressLabel = computed(() => {
    const st = this.blobState();
    if (!st?.bytes_total) return 'Uploading…';
    const mb = (n: number) => (n / 1024 / 1024).toFixed(1);
    return `Uploading… ${this.blobProgress()}% (${mb(st.bytes_sent ?? 0)} / ${mb(st.bytes_total)} MB)`;
  });
  protected readonly blobError = computed(() =>
    this.blobState()?.error ?? (this.blobStatus() === 'failed' ? 'Upload timed out' : ''),
  );
  /** Actions disabled while processing */
  protected readonly actionsDisabled = computed(() => this.isProcessing());

  protected onBlobUpload(event: Event): void {
    event.stopPropagation();
    if (['uploaded', 'queued', 'uploading'].includes(this.blobStatus())) return;
    this.blobUpload.emit(this.recording());
  }

  protected onBlobCancel(event: Event): void {
    event.stopPropagation();
    this.blobCancel.emit(this.recording());
  }

  protected onPlay(event: Event): void {
    if (this.actionsDisabled()) return;
    event.stopPropagation();
    this.play.emit(this.recording());
  }

  protected onDownload(event: Event): void {
    if (this.actionsDisabled()) return;
    event.stopPropagation();
    this.download.emit(this.recording());
  }

  protected isRenaming = signal(false);
  protected renameValue = signal('');
  private readonly renameInputRef = viewChild<ElementRef<HTMLInputElement>>('renameInput');

  protected startRename(event: Event): void {
    event.stopPropagation();
    this.renameValue.set(this.recording().name);
    this.isRenaming.set(true);
    setTimeout(() => {
      const el = this.renameInputRef()?.nativeElement;
      if (el) {
        el.focus();
        el.select();
      }
    });
  }

  protected commitRename(event: Event): void {
    event.stopPropagation();
    const name = this.renameValue().trim();
    if (name && name !== this.recording().name) {
      this.rename.emit({ recording: this.recording(), name });
    }
    this.isRenaming.set(false);
  }

  protected cancelRename(event: Event): void {
    event.stopPropagation();
    this.isRenaming.set(false);
  }

  protected onRenameKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter') this.commitRename(event);
    else if (event.key === 'Escape') this.cancelRename(event);
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
}
