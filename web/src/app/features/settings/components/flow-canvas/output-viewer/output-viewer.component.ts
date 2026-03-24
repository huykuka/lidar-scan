import {Component, computed, effect, ElementRef, inject, OnDestroy, signal, viewChild} from '@angular/core';
import {DatePipe} from '@angular/common';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {MultiWebsocketService} from '@core/services/multi-websocket.service';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {environment} from '@env/environment';
import {Subscription} from 'rxjs';

export interface OutputMessage {
  node_id: string;
  timestamp: number;
  metadata: Record<string, unknown>;
  receivedAt: Date;
}

const OUTPUT_TOPIC = 'output';
/** Maximum messages kept in memory — older ones are evicted to avoid unbounded growth. */
const MAX_MESSAGES = 500;
/** Maximum messages rendered in the DOM at one time. */
const RENDER_WINDOW = 100;

@Component({
  selector: 'app-output-viewer',
  imports: [SynergyComponentsModule, DatePipe],
  templateUrl: './output-viewer.component.html',
  styleUrl: './output-viewer.component.css',
})
export class OutputViewerComponent implements OnDestroy {
  isCollapsed = signal<boolean>(false);
  isFrozen = signal<boolean>(false);

  /** Full live message buffer — capped at MAX_MESSAGES. Always updated by WS. */
  private allMessages = signal<OutputMessage[]>([]);

  /**
   * Snapshot taken at the moment the user clicks "freeze".
   * When frozen this is what the template renders instead of the live window.
   */
  private frozenSnapshot = signal<OutputMessage[]>([]);

  /** Slice exposed to the template. Frozen → snapshot. Live → last RENDER_WINDOW. */
  readonly visibleMessages = computed<OutputMessage[]>(() => {
    if (this.isFrozen()) return this.frozenSnapshot();
    const all = this.allMessages();
    return all.length > RENDER_WINDOW ? all.slice(all.length - RENDER_WINDOW) : all;
  });

  /** Total buffered count shown in the header badge. */
  readonly totalCount = computed(() => this.allMessages().length);

  /** node_id → human-readable name derived from the global node store. */
  private readonly nodeStore = inject(NodeStoreService);
  private readonly nodeNameMap = computed<Map<string, string>>(() =>
    new Map(this.nodeStore.nodes().map((n) => [n.id, n.name])),
  );

  private readonly wsService = inject(MultiWebsocketService);
  private subscription?: Subscription;
  private logRef = viewChild<ElementRef<HTMLDivElement>>('logContainer');

  constructor() {
    // Connect WS when panel opens, disconnect when panel collapses.
    effect(() => {
      if (this.isCollapsed()) {
        this.disconnectWs();
      } else {
        this.connectWs();
      }
    });

    // Auto-scroll to bottom only when live (not frozen) and panel is open.
    effect(() => {
      const msgs = this.visibleMessages();
      if (msgs.length === 0 || this.isCollapsed() || this.isFrozen()) return;
      const el = this.logRef()?.nativeElement;
      if (el) {
        queueMicrotask(() => { el.scrollTop = el.scrollHeight; });
      }
    });
  }

  ngOnDestroy(): void {
    this.disconnectWs();
  }

  toggleCollapse(): void {
    // Unfreeze whenever collapsing so state is clean on next open.
    if (!this.isCollapsed()) this.isFrozen.set(false);
    this.isCollapsed.update(v => !v);
  }

  toggleFreeze(): void {
    if (this.isFrozen()) {
      // Unfreeze — discard snapshot, resume live view.
      this.isFrozen.set(false);
      this.frozenSnapshot.set([]);
    } else {
      // Freeze — snapshot the current visible window.
      this.frozenSnapshot.set(this.visibleMessages());
      this.isFrozen.set(true);
    }
  }

  clearMessages(): void {
    this.allMessages.set([]);
    this.frozenSnapshot.set([]);
    this.isFrozen.set(false);
  }

  /** Resolve a node_id to its human-readable name, falling back to the raw id. */
  nodeName(id: string): string {
    return this.nodeNameMap().get(id) ?? id;
  }

  readonly objectKeys = Object.keys;

  private connectWs(): void {
    if (this.subscription) return; // already connected
    const url = environment.wsUrl(OUTPUT_TOPIC);
    this.subscription = this.wsService.connect(OUTPUT_TOPIC, url).subscribe({
      next: (data) => this.handleMessage(data),
      error: () => (this.subscription = undefined),
      complete: () => (this.subscription = undefined),
    });
  }

  private disconnectWs(): void {
    this.subscription?.unsubscribe();
    this.subscription = undefined;
    this.wsService.disconnect(OUTPUT_TOPIC);
  }

  private handleMessage(data: unknown): void {
    try {
      const raw = typeof data === 'string' ? JSON.parse(data) : data;
      if (raw?.type !== 'output_node_metadata') return;

      const msg: OutputMessage = {
        node_id: raw.node_id ?? 'unknown',
        timestamp: raw.timestamp ?? Date.now() / 1000,
        metadata: raw.metadata ?? {},
        receivedAt: new Date(),
      };

      // Always buffer, even when frozen — user sees new count on unfreeze.
      this.allMessages.update((prev) => {
        const next = [...prev, msg];
        return next.length > MAX_MESSAGES ? next.slice(next.length - MAX_MESSAGES) : next;
      });
    } catch {
      // Silently drop unparseable frames (e.g. binary LIDR frames on this topic).
    }
  }
}
