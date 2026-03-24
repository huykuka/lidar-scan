import {Component, computed, effect, ElementRef, inject, OnDestroy, signal, viewChild} from '@angular/core';
import {DatePipe} from '@angular/common';
import {DomSanitizer, SafeHtml} from '@angular/platform-browser';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {MultiWebsocketService} from '@core/services/multi-websocket.service';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {environment} from '@env/environment';
import {Subscription} from 'rxjs';

export interface OutputMessage {
  type: string;
  node_id: string;
  timestamp: number;
  metadata: unknown;
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
  protected readonly nodeName = computed<Map<string, string>>(() =>
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

  private readonly sanitizer = inject(DomSanitizer);

  /** Returns syntax-highlighted HTML for any JSON-serialisable value. */
  formatJson(payload: unknown): SafeHtml {
    const json = JSON.stringify(payload, null, 2);
    const html = json.replace(
      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
      (match) => {
        if (/^"/.test(match)) {
          if (/:$/.test(match)) {
            return `<span class="json-key">${match}</span>`;
          }
          return `<span class="json-str">${match}</span>`;
        }
        if (/true|false/.test(match)) {
          return `<span class="json-bool">${match}</span>`;
        }
        if (/null/.test(match)) {
          return `<span class="json-null">${match}</span>`;
        }
        return `<span class="json-num">${match}</span>`;
      },
    );
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }

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
      const parsed = typeof data === 'string' ? JSON.parse(data) : data;
      const msg: OutputMessage = {
        type: (parsed as any).type ?? '',
        node_id: (parsed as any).node_id ?? '',
        timestamp: (parsed as any).timestamp ?? Date.now() / 1000,
        metadata: (parsed as any).metadata ?? {},
        receivedAt: new Date(),
      };
      this.allMessages.update((prev) => {
        const next = [...prev, msg];
        return next.length > MAX_MESSAGES ? next.slice(next.length - MAX_MESSAGES) : next;
      });
    } catch {
    }
  }
}

