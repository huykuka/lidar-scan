import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpContext } from '@angular/common/http';
import { catchError, interval, of, switchMap, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ToastService } from './toast.service';
import { TOAST_ON_ERROR } from '../interceptors/http-toast.interceptor';
import { firstValueFrom } from 'rxjs';

export type SystemNoticeLevel = 'info' | 'warning' | 'error';

export interface SystemNotice {
  level: SystemNoticeLevel;
  message: string;
  at: number;
}

interface BackendStatusResponse {
  is_running?: boolean;
  active_sensors?: string[];
  version?: string;
}

@Injectable({
  providedIn: 'root',
})
export class SystemStatusService {
  private http = inject(HttpClient);
  private toast = inject(ToastService);
  private destroyRef = inject(DestroyRef);

  private started = false;
  private lastOnlineToastAt = 0;
  private lastOfflineToastAt = 0;

  readonly backendOnline = signal<boolean | null>(null);
  readonly backendVersion = signal<string | null>(null);
  readonly activeSensors = signal<string[]>([]);
  readonly unreadCount = signal<number>(0);
  readonly lastNotice = signal<SystemNotice | null>(null);
  readonly isRunning = signal<boolean>(false);

  readonly backendLabel = computed(() => {
    const online = this.backendOnline();
    if (online === null) return 'Checking';
    return online ? 'Online' : 'Offline';
  });

  async startSystem(): Promise<void> {
    const res = await firstValueFrom(
      this.http.post<BackendStatusResponse>(`${environment.apiUrl}/start`, {}),
    );
    if (res) this.isRunning.set(res.is_running ?? true);
  }

  async stopSystem(): Promise<void> {
    const res = await firstValueFrom(
      this.http.post<BackendStatusResponse>(`${environment.apiUrl}/stop`, {}),
    );
    if (res) this.isRunning.set(res.is_running ?? false);
  }

  start(pollMs: number = 10000): void {
    if (this.started) return;
    this.started = true;

    // Run an immediate check before interval pipeline (for fast header feedback).
    this.fetchStatus$().pipe(takeUntilDestroyed(this.destroyRef)).subscribe();

    interval(pollMs)
      .pipe(
        switchMap(() => this.fetchStatus$()),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }

  refreshNow(): void {
    this.fetchStatus$().pipe(takeUntilDestroyed(this.destroyRef)).subscribe();
  }

  acknowledge(): void {
    this.unreadCount.set(0);
  }

  report(level: SystemNoticeLevel, message: string): void {
    this.lastNotice.set({ level, message, at: Date.now() });
    this.unreadCount.update((c) => c + 1);
  }

  private fetchStatus$() {
    // Avoid showing HTTP interceptor toasts for this health check.
    const ctx = new HttpContext().set(TOAST_ON_ERROR, false);
    return this.http
      .get<BackendStatusResponse>(`${environment.apiUrl}/status`, { context: ctx })
      .pipe(
        tap((res) => {
          const wasOnline = this.backendOnline();
          this.backendOnline.set(true);
          this.backendVersion.set(res?.version ?? null);
          this.activeSensors.set(Array.isArray(res?.active_sensors) ? res.active_sensors : []);
          this.isRunning.set(res?.is_running ?? false);

          if (wasOnline === false) this.maybeToastOnline();
        }),
        catchError(() => {
          const wasOnline = this.backendOnline();
          this.backendOnline.set(false);
          this.backendVersion.set(null);
          this.activeSensors.set([]);

          if (wasOnline !== false) this.maybeToastOffline();
          return of(null);
        }),
      );
  }

  private maybeToastOnline(): void {
    const now = Date.now();
    if (now - this.lastOnlineToastAt < 30000) return;
    this.lastOnlineToastAt = now;
    this.toast.success('Backend connected.');
    this.report('info', 'Backend connected.');
  }

  private maybeToastOffline(): void {
    const now = Date.now();
    if (now - this.lastOfflineToastAt < 30000) return;
    this.lastOfflineToastAt = now;
    this.toast.warning('Backend unreachable. Some actions may fail.');
    this.report('warning', 'Backend unreachable.');
  }
}
