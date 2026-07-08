import {
  ChangeDetectionStrategy,
  Component,
  computed,
  CUSTOM_ELEMENTS_SCHEMA,
  effect,
  inject,
  OnDestroy,
  signal,
  viewChildren,
} from '@angular/core';

import {Subscription} from 'rxjs';
import {MultiWebsocketService} from '@core/services/multi-websocket.service';
import {DEFAULT_TOPIC_COLORS} from '@core/services/stores/workspace-store.service';
import {environment} from '@env/environment';
import {NgtsPointsBuffer} from 'angular-three-soba/performances';
import {NgtCanvas, NgtCanvasContent, NgtCanvasImpl} from 'angular-three/dom';
import {ThreedSceneGraphComponent} from '@shared/components';
import {SynergyComponentsModule} from '@synergy-design-system/angular';

export interface PreviewTopic {
  nodeId: string;
  nodeName: string;
  topic: string;
  color: string;
  pointSize: number;
}

/**
 * Live 3D point cloud preview panel for the Settings page.
 * Manages its own WebSocket connections independently from the workspace.
 * Only renders topics explicitly added via right-click context menu on nodes.
 */
@Component({
  selector: 'app-settings-preview-panel',
  templateUrl: './settings-preview-panel.component.html',
  styleUrl: './settings-preview-panel.component.css',
  imports: [
    NgtCanvas,
    ThreedSceneGraphComponent,
    NgtsPointsBuffer,
    NgtCanvasImpl,
    NgtCanvasContent,
    SynergyComponentsModule,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  providers: [MultiWebsocketService], // Own instance, isolated from workspace
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsPreviewPanelComponent implements OnDestroy {
  private readonly wsService = inject(MultiWebsocketService);

  /** Topics explicitly selected for preview via node context menu */
  readonly previewTopics = signal<PreviewTopic[]>([]);

  /** Latest frame data per topic (positions Float32Array + count) */
  readonly frames = signal<Map<string, { points: Float32Array; count: number }>>(new Map());

  readonly isConnected = signal(false);
  readonly showGrid = signal(true);
  readonly topicCount = computed(() => this.previewTopics().length);

  readonly MAX_POINTS = 250_000;
  private readonly staticBuffers = new Map<string, Float32Array>();
  private readonly subscriptions = new Map<string, Subscription>();

  protected readonly topicEntries = computed(() =>
    this.previewTopics().map((t) => {
      if (!this.staticBuffers.has(t.topic)) {
        this.staticBuffers.set(t.topic, new Float32Array(this.MAX_POINTS * 3));
      }
      return {
        topic: t.topic,
        color: t.color,
        pointSize: t.pointSize,
        buf: this.staticBuffers.get(t.topic)!,
      };
    }),
  );

  private readonly pointsBuffers = viewChildren<NgtsPointsBuffer>('buf');

  protected readonly topicFrames = computed(() =>
    this.topicEntries().map((entry) => ({
      entry,
      frame: this.frames().get(entry.topic) ?? null,
    })),
  );

  constructor() {
    // Update Three.js buffers when frames arrive
    effect(() => {
      const pairs = this.topicFrames();
      const bufs = this.pointsBuffers();

      pairs.forEach(({entry, frame}, i) => {
        const points = bufs[i]?.pointsRef()?.nativeElement;
        if (!points) return;

        if (!frame || frame.count === 0) {
          points.visible = false;
          return;
        }
        points.visible = true;

        const count = Math.min(frame.count, this.MAX_POINTS);
        entry.buf.set(frame.points.subarray(0, count * 3));

        const geo = points.geometry;
        if (!geo) return;
        geo.setDrawRange(0, count);
        const attr = geo.attributes['position'];
        if (attr) attr.needsUpdate = true;
      });
    });
  }

  /** Add a node's topic to the preview and open its WebSocket connection. */
  addPreviewTopic(nodeId: string, nodeName: string, topic: string): void {
    const current = this.previewTopics();
    if (current.some((t) => t.topic === topic)) return;
    const colorIndex = current.length % DEFAULT_TOPIC_COLORS.length;
    this.previewTopics.set([
      ...current,
      { nodeId, nodeName, topic, color: DEFAULT_TOPIC_COLORS[colorIndex], pointSize: 2 },
    ]);
    this._connectTopic(topic);
  }

  /** Remove a node's topic from the preview and close its WebSocket. */
  removePreviewTopic(topic: string): void {
    this.previewTopics.update((topics) => topics.filter((t) => t.topic !== topic));
    this._disconnectTopic(topic);
    this.staticBuffers.delete(topic);
    this.frames.update((m) => {
      const next = new Map(m);
      next.delete(topic);
      return next;
    });
  }

  /** Check if a node is currently being previewed. */
  isNodePreviewed(nodeId: string): boolean {
    return this.previewTopics().some((t) => t.nodeId === nodeId);
  }

  ngOnDestroy(): void {
    // 1. Disconnect all WebSockets and unsubscribe
    this.subscriptions.forEach((sub) => sub.unsubscribe());
    this.subscriptions.clear();
    this.wsService.disconnectAll();

    // 2. Dispose Three.js geometries and materials
    this.pointsBuffers().forEach((buf) => {
      const points = buf.pointsRef?.()?.nativeElement;
      if (!points) return;
      points.geometry?.dispose();
      const mat = points.material;
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
      else mat?.dispose();
    });

    // 3. Release all Float32Array buffers
    this.staticBuffers.clear();

    // 4. Clear frame data references
    this.frames.set(new Map());

    // 5. Clear topic list
    this.previewTopics.set([]);
  }

  // -- Private WebSocket management --

  private _connectTopic(topic: string): void {
    if (this.subscriptions.has(topic)) return;
    const url = environment.wsUrl(topic);
    const sub = this.wsService.connect(topic, url).subscribe({
      next: (data: any) => this._handleMessage(topic, data),
    });
    this.subscriptions.set(topic, sub);
    this.isConnected.set(true);
  }

  private _disconnectTopic(topic: string): void {
    const sub = this.subscriptions.get(topic);
    if (sub) {
      sub.unsubscribe();
      this.subscriptions.delete(topic);
    }
    this.wsService.disconnect(topic);
    this.isConnected.set(this.subscriptions.size > 0);
  }

  private _handleMessage(topic: string, data: any): void {
    if (data instanceof ArrayBuffer) {
      const parsed = this._parseLidrBinary(data);
      if (!parsed) return;
      this.frames.update((m) => {
        const next = new Map(m);
        next.set(topic, parsed);
        return next;
      });
    }
  }

  /**
   * Parse LIDR binary format:
   * magic[4] "LIDR" | version:u32 | timestamp:f64 | count:u32 | points:f32[N*3]
   * Header = 20 bytes, points start at offset 20.
   */
  private _parseLidrBinary(buffer: ArrayBuffer): { points: Float32Array; count: number } | null {
    if (buffer.byteLength < 20) return null;

    const view = new DataView(buffer);
    const magic =
      String.fromCharCode(view.getUint8(0)) +
      String.fromCharCode(view.getUint8(1)) +
      String.fromCharCode(view.getUint8(2)) +
      String.fromCharCode(view.getUint8(3));

    if (magic !== 'LIDR') return null;

    const count = view.getUint32(16, true);
    const points = new Float32Array(buffer, 20, count * 3);

    return { points, count };
  }
}
