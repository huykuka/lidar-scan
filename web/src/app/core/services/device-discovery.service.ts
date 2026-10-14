import {computed, DestroyRef, inject, Injectable, signal} from '@angular/core';
import {HttpClient, HttpErrorResponse} from '@angular/common/http';
import {firstValueFrom, Subscription} from 'rxjs';
import {environment} from '@env/environment';
import {AuthService} from '@core/services/auth.service';
import {MultiWebsocketService} from '@core/services/multi-websocket.service';
import {ScanJob} from '@core/models/device-discovery.model';

const WS_TOPIC = 'device_discovery';

@Injectable({providedIn: 'root'})
export class DeviceDiscoveryService {
  private readonly http = inject(HttpClient);
  private readonly ws = inject(MultiWebsocketService);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);

  private readonly _job = signal<ScanJob | null>(null);
  private readonly _loading = signal(false);
  private readonly _starting = signal(false);
  private readonly _error = signal<string | null>(null);

  readonly job = this._job.asReadonly();
  /** True during initial GET. */
  readonly loading = this._loading.asReadonly();
  /** True while POST scan in flight. */
  readonly starting = this._starting.asReadonly();
  readonly error = this._error.asReadonly();
  readonly isRunning = computed(() => this._job()?.status === 'running');

  private sub: Subscription | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private active = false;

  constructor() {
    this.destroyRef.onDestroy(() => this.disconnect());
  }

  async getScan(): Promise<void> {
    this._loading.set(true);
    this._error.set(null);
    try {
      const job = await firstValueFrom(
        this.http.get<ScanJob | null>(`${environment.apiUrl}/discovery/scan`),
      );
      this.applyJob(job);
    } catch (e) {
      this._error.set(this.mapError(e));
    } finally {
      this._loading.set(false);
    }
  }

  async startScan(cidrs?: string[]): Promise<void> {
    this._starting.set(true);
    this._error.set(null);
    try {
      const body = cidrs && cidrs.length > 0 ? {cidrs} : {};
      const job = await firstValueFrom(
        this.http.post<ScanJob>(`${environment.apiUrl}/discovery/scan`, body),
      );
      this.applyJob(job);
    } catch (e) {
      this._error.set(this.mapError(e));
    } finally {
      this._starting.set(false);
    }
  }

  /** Open WS; call when drawer opens. Snapshot arrives on connect. */
  connect(): void {
    this.active = true;
    this.syncPolling();
    if (this.sub) return;
    // Backend requires JWT via query param (browsers cannot set WS headers).
    const token = this.auth.getToken();
    const url = environment.wsUrl(WS_TOPIC) + (token ? `?token=${encodeURIComponent(token)}` : '');
    this.sub = this.ws.connect(WS_TOPIC, url).subscribe({
      next: (data) => this.onMessage(data),
      error: () => this.cleanupSub(),
      complete: () => this.cleanupSub(),
    });
  }

  /** Close WS; call when drawer closes. */
  disconnect(): void {
    this.active = false;
    this.stopPolling();
    this.sub?.unsubscribe();
    this.sub = null;
    this.ws.disconnect(WS_TOPIC);
  }

  clearError(): void {
    this._error.set(null);
  }

  /** Fallback: poll GET every 1s while connected + running (covers WS gaps/drops). */
  private syncPolling(): void {
    const shouldPoll = this.active && this._job()?.status === 'running';
    if (shouldPoll && !this.pollTimer) {
      this.pollTimer = setInterval(() => void this.pollOnce(), 1000);
    } else if (!shouldPoll) {
      this.stopPolling();
    }
  }

  private stopPolling(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  private async pollOnce(): Promise<void> {
    try {
      const job = await firstValueFrom(
        this.http.get<ScanJob | null>(`${environment.apiUrl}/discovery/scan`),
      );
      if (this.active) this.applyJob(job);
    } catch {
      /* transient; next tick retries */
    }
  }

  private cleanupSub(): void {
    this.sub = null;
  }

  private onMessage(data: unknown): void {
    if (typeof data !== 'string') return;
    try {
      const job = JSON.parse(data) as ScanJob | null;
      if (job) this.applyJob(job);
    } catch {
      /* ignore malformed frame */
    }
  }

  private applyJob(job: ScanJob | null): void {
    this._job.set(job);
    this.syncPolling();
    if (job?.status === 'failed') {
      this._error.set(job.error ?? 'Scan failed');
    } else if (job?.status === 'running') {
      this._error.set(null);
    }
  }

  private mapError(e: unknown): string {
    if (e instanceof HttpErrorResponse) {
      if (e.status === 0) return 'Network error. Backend unreachable.';
      if (e.status === 403) return 'You do not have permission to scan for devices.';
      const d = e.error?.detail;
      if (e.status === 422 && d && typeof d === 'object') {
        switch (d.code) {
          case 'invalid_cidr':
            return `Invalid CIDR${d.cidr ? ` "${d.cidr}"` : ''}. Use format like 192.168.1.0/24.`;
          case 'too_many_hosts':
            return `Too many hosts to scan (${d.total ?? '?'}, max ${d.max ?? '?'}). Use a smaller range.`;
          case 'no_subnet':
            return 'No local subnet detected. Enter a CIDR manually.';
        }
        if (d.message) return String(d.message);
      }
      if (typeof d === 'string') return d;
    }
    return 'Unexpected error while contacting discovery service.';
  }
}
