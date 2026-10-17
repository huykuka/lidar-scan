import {inject, Injectable, signal} from '@angular/core';
import {Subscription} from 'rxjs';
import {HttpEventType} from '@angular/common/http';
import {RecordingApiService} from './api/recording-api.service';
import {RecordingStoreService} from './stores/recording-store.service';

export type UploadStatus = 'queued' | 'uploading' | 'processing' | 'done' | 'error';

export interface UploadItem {
  id: number;
  name: string;
  size: number;
  progress: number; // 0-100
  status: UploadStatus;
  error?: string;
}

const MAX_CONCURRENT = 2;

@Injectable({providedIn: 'root'})
export class RecordingUploadService {
  private api = inject(RecordingApiService);
  private store = inject(RecordingStoreService);

  readonly items = signal<UploadItem[]>([]);
  private files = new Map<number, File>();
  private subs = new Map<number, Subscription>();
  private nextId = 1;

  enqueue(files: File[]): void {
    const added = files.map((f): UploadItem => {
      const id = this.nextId++;
      this.files.set(id, f);
      return {id, name: f.name, size: f.size, progress: 0, status: 'queued'};
    });
    this.items.update((list) => [...list, ...added]);
    this.pump();
  }

  retry(id: number): void {
    this.patch(id, {status: 'queued', progress: 0, error: undefined});
    this.pump();
  }

  /** Abort a queued or in-flight transfer (aborting the request stops the browser sending) and drop it. */
  cancel(id: number): void {
    this.subs.get(id)?.unsubscribe();
    this.subs.delete(id);
    this.dismiss(id);
    this.pump();
  }

  dismiss(id: number): void {
    this.files.delete(id);
    this.items.update((list) => list.filter((i) => i.id !== id));
  }

  clearFinished(): void {
    this.items.update((list) => list.filter((i) => i.status === 'queued' || i.status === 'uploading' || i.status === 'processing'));
  }

  private pump(): void {
    const active = this.items().filter((i) => i.status === 'uploading' || i.status === 'processing').length;
    const slots = MAX_CONCURRENT - active;
    this.items()
      .filter((i) => i.status === 'queued')
      .slice(0, Math.max(0, slots))
      .forEach((i) => this.start(i.id));
  }

  private start(id: number): void {
    const file = this.files.get(id);
    if (!file) return;
    this.patch(id, {status: 'uploading', progress: 0});
    const sub = this.api.uploadRecordingWithProgress(file).subscribe({
      next: (event) => {
        if (event.type === HttpEventType.UploadProgress) {
          const pct = event.total ? Math.round((event.loaded / event.total) * 100) : 0;
          this.patch(id, {progress: pct, status: pct >= 100 ? 'processing' : 'uploading'});
        } else if (event.type === HttpEventType.Response) {
          this.patch(id, {progress: 100, status: 'done'});
          this.files.delete(id);
          this.store.refresh();
        }
      },
      error: (err) => {
        this.patch(id, {status: 'error', error: err?.error?.detail ?? err?.message ?? 'Upload failed.'});
        this.pump();
      },
      complete: () => {
        this.subs.delete(id);
        this.pump();
      },
    });
    this.subs.set(id, sub);
  }

  private patch(id: number, changes: Partial<UploadItem>): void {
    this.items.update((list) => list.map((i) => (i.id === id ? {...i, ...changes} : i)));
  }
}
