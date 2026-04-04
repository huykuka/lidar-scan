import {inject, Injectable, signal} from '@angular/core';
import {Subscription} from 'rxjs';
import {environment} from '@env/environment';
import {NodesStatusResponse} from '@core/models';
import {SystemStatusBroadcast} from '@core/models/status.model';
import {MultiWebsocketService} from './multi-websocket.service';
import {MOCK_SYSTEM_STATUS, startMockStatusCycling} from './mock-status.helper';
import {SystemStatusService} from './system-status.service';

const STATUS_TOPIC = 'system_status';
const DEBOUNCE_MS = 50;

/**
 * Owns the `system_status` WebSocket topic.
 * Exposes a typed, debounced `status` signal and a `connected` signal.
 * Transport is delegated to MultiWebsocketService.
 *
 * Also forwards any `reload_event` fields from the broadcast to
 * SystemStatusService so the reload indicator signals stay in sync.
 */
@Injectable({
  providedIn: 'root',
})
export class NodeStatusService {
  readonly status = signal<NodesStatusResponse | null>(null);
  readonly connected = signal<boolean>(false);

  private readonly wsService = inject(MultiWebsocketService);
  private readonly systemStatus = inject(SystemStatusService);
  private subscription: Subscription | null = null;
  private debounceId: ReturnType<typeof setTimeout> | null = null;
  private pending: NodesStatusResponse | null = null;
  private mockCleanup: (() => void) | null = null;

  connect(): void {
    if ((environment as any).mockStatus === true) {
      console.warn('[NodeStatusService] Mock mode enabled — using cycling mock data');
      this.status.set(MOCK_SYSTEM_STATUS);
      this.connected.set(true);
      this.mockCleanup = startMockStatusCycling(this.status);
      return;
    }

    if (this.subscription) return;

    const url = environment.wsUrl(STATUS_TOPIC);

    this.subscription = this.wsService.connect(STATUS_TOPIC, url).subscribe({
      next: (raw: any) => {
        try {
          const data: SystemStatusBroadcast =
            typeof raw === 'string' ? JSON.parse(raw) : raw;

          // Forward reload events to SystemStatusService
          if (data.reload_event) {
            this.systemStatus.applyReloadEvent(data.reload_event);
          }

          // Cast to NodesStatusResponse for the existing status signal consumers
          this.pending = data as unknown as NodesStatusResponse;
          if (!this.debounceId) {
            this.debounceId = setTimeout(() => {
              if (this.pending) this.status.set(this.pending);
              this.pending = null;
              this.debounceId = null;
            }, DEBOUNCE_MS);
          }

          if (!this.connected()) this.connected.set(true);
        } catch {
          console.error('[NodeStatusService] Failed to parse message');
        }
      },
      error: () => {
        this.connected.set(false);
        this.subscription = null;
        this.systemStatus.clearReloadingState();
      },
      complete: () => {
        this.connected.set(false);
        this.subscription = null;
        this.systemStatus.clearReloadingState();
      },
    });

    this.connected.set(true);
  }

  disconnect(): void {
    this.mockCleanup?.();
    this.mockCleanup = null;

    if (this.debounceId) {
      clearTimeout(this.debounceId);
      this.debounceId = null;
    }
    this.pending = null;

    this.subscription?.unsubscribe();
    this.subscription = null;
    this.wsService.disconnect(STATUS_TOPIC);
    this.connected.set(false);
    this.systemStatus.clearReloadingState();
  }
}
