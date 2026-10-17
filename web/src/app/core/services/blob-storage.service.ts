import {effect, inject, Injectable, signal, untracked} from '@angular/core';
import {catchError, firstValueFrom, of} from 'rxjs';
import {AuthService} from './auth.service';
import {RecordingApiService} from './api/recording-api.service';

/**
 * Tracks whether recording upload to S3-compatible blob storage is usable.
 * Only service users ever query it; for everyone else it stays unavailable.
 * Checked at app boot (AppInitService) and again whenever the signed-in user changes.
 */
@Injectable({providedIn: 'root'})
export class BlobStorageService {
  private readonly auth = inject(AuthService);
  private readonly api = inject(RecordingApiService);

  /** Configured on the server AND credentials verified. */
  readonly available = signal(false);
  /** Why it is unavailable (shown in the button tooltip). */
  readonly reason = signal<string | null>(null);

  constructor() {
    effect(() => {
      const isService = this.auth.isService();
      untracked(() => void (isService ? this.refresh() : this.reset()));
    });
  }

  async refresh(): Promise<void> {
    if (!this.auth.isService()) return this.reset();
    const status = await firstValueFrom(this.api.getBlobStorageStatus().pipe(catchError(() => of(null))));
    this.available.set(!!status?.available);
    this.reason.set(status ? (status.available ? null : (status.reason ?? 'Unavailable')) : 'Status check failed');
  }

  private reset(): void {
    this.available.set(false);
    this.reason.set(null);
  }
}
