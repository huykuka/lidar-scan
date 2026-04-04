import {computed, DestroyRef, inject, Injectable, signal} from '@angular/core';
import {HttpClient, HttpContext} from '@angular/common/http';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
import {catchError, firstValueFrom, interval, of, switchMap, tap} from 'rxjs';
import {environment} from '../../../environments/environment';
import {ToastService} from './toast.service';
import {TOAST_ON_ERROR} from '../interceptors/http-toast.interceptor';
import {ReloadEvent} from '@core/models/status.model';

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

  // ------ Reload event signals ------
  private _reloadingNodeIds = signal<Set<string>>(new Set());
  private _lastReloadEvent = signal<ReloadEvent | null>(null);
  readonly reloadingNodeIds = this._reloadingNodeIds.asReadonly();
  readonly lastReloadEvent = this._lastReloadEvent.asReadonly();

  private http = inject(HttpClient);
  private toast = inject(ToastService);
  private destroyRef = inject(DestroyRef);
  private started = false;
  private lastOnlineToastAt = 0;
  private lastOfflineToastAt = 0;

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
    this.lastNotice.set({level, message, at: Date.now()});
    this.unreadCount.update((c) => c + 1);
  }

  private fetchStatus$() {
    // Avoid showing HTTP interceptor toasts for this health check.
    const ctx = new HttpContext().set(TOAST_ON_ERROR, false);
    return this.http
      .get<BackendStatusResponse>(`${environment.apiUrl}/status`, {context: ctx})
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

  /**
   * Apply a reload event received from the WebSocket broadcast.
   * Called by NodeStatusService when it parses a `reload_event` field
   * from the `system_status` topic message.
   */
  applyReloadEvent(event: ReloadEvent): void {
    this._lastReloadEvent.set(event);

    if (!event.node_id) {
      // Full reload — clear all per-node reload indicators
      this._reloadingNodeIds.set(new Set());
    } else if (event.status === 'reloading') {
      this._reloadingNodeIds.update((ids) => new Set([...ids, event.node_id!]));
    } else if (event.status === 'ready' || event.status === 'error') {
      this._reloadingNodeIds.update((ids) => {
        const next = new Set(ids);
        next.delete(event.node_id!);
        return next;
      });
    }
  }

  /** Clear all reload state (called on WebSocket disconnect/reconnect). */
  clearReloadingState(): void {
    this._reloadingNodeIds.set(new Set());
    this._lastReloadEvent.set(null);
  }

  /**
   * Dev/test helper — simulates a selective reload sequence for a given node.
   * Guarded by !environment.production so it never ships to prod.
   */
  triggerMockReloadSequence(nodeId: string): void {
    if ((environment as any).production) return;

    this.applyReloadEvent({
      node_id: nodeId,
      status: 'reloading',
      error_message: null,
      reload_mode: 'selective',
      timestamp: Date.now() / 1000,
    });

    setTimeout(() => {
      this.applyReloadEvent({
        node_id: nodeId,
        status: 'ready',
        error_message: null,
        reload_mode: 'selective',
        timestamp: Date.now() / 1000,
      });
    }, 800);
  }
}
