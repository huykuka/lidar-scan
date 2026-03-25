import {effect, inject, Injectable, OnDestroy, signal} from '@angular/core';
import {Subscription} from 'rxjs';
import {MultiWebsocketService} from './multi-websocket.service';
import {TopicConfig, WorkspaceStoreService} from '@core/services/stores';
import {FramePayload, parseJsonPointCloud, parseLidrFrame} from './lidr-parser';
import {environment} from '@env/environment';

export type { FramePayload };

@Injectable({ providedIn: 'root' })
export class PointCloudDataService implements OnDestroy {
  // ── Public Signals ────────────────────────────────────────────────────────

  /**
   * Latest decoded frame per topic.
   * Keyed by topic name (e.g. "lidar_1").
   * Empty map = no data / disconnected.
   */
  readonly frames = signal<Map<string, FramePayload>>(new Map());

  /**
   * True when at least one topic WS is currently OPEN.
   */
  readonly isConnected = signal(false);

  // ── Private State ─────────────────────────────────────────────────────────

  private wsService       = inject(MultiWebsocketService);
  private workspaceStore  = inject(WorkspaceStoreService);

  private subscriptions      = new Map<string, Subscription>();
  private frameCountPerTopic = new Map<string, number>();
  private readonly fpsInterval?: ReturnType<typeof setInterval>;

  constructor() {
    // React to topic selection changes → sync WebSocket connections
    effect(() => {
      const selectedTopics = this.workspaceStore.selectedTopics();
      this.syncConnections(selectedTopics);
    });

    // FPS counter: accumulate per-topic frame counts, publish to store each second
    this.fpsInterval = setInterval(() => this.updateFps(), 1000);
  }

  ngOnDestroy(): void {
    this.subscriptions.forEach(s => s.unsubscribe());
    this.subscriptions.clear();
    this.wsService.disconnectAll();
    if (this.fpsInterval !== undefined) {
      clearInterval(this.fpsInterval);
    }
  }

  // ── Private Methods ───────────────────────────────────────────────────────

  /**
   * Synchronise active WebSocket connections with the current list of
   * enabled topics from the workspace store.
   */
  private syncConnections(selectedTopics: TopicConfig[]): void {
    const enabledTopics   = selectedTopics.filter(t => t.enabled);
    const enabledTopicSet = new Set(enabledTopics.map(t => t.topic));

    // Disconnect topics that are no longer enabled
    this.subscriptions.forEach((_, topic) => {
      if (!enabledTopicSet.has(topic)) {
        this.disconnectTopic(topic);
      }
    });

    // Connect newly enabled topics
    enabledTopics.forEach(({ topic }) => {
      if (!this.subscriptions.has(topic)) {
        this.connectTopic(topic);
      }
    });

    // Update connection status
    this.isConnected.set(enabledTopics.length > 0);
  }

  private connectTopic(topic: string): void {
    if (this.subscriptions.has(topic)) return;

    const url = environment.wsUrl(topic);
    const subscription = this.wsService.connect(topic, url).subscribe({
      next: (data: any)  => this.handleMessage(topic, data),
      complete: ()       => this.onTopicComplete(topic),
      error: ()          => this.onTopicError(topic),
    });

    this.subscriptions.set(topic, subscription);
    this.frameCountPerTopic.set(topic, 0);
  }

  private disconnectTopic(topic: string): void {
    const sub = this.subscriptions.get(topic);
    if (sub) {
      sub.unsubscribe();
      this.subscriptions.delete(topic);
    }
    this.wsService.disconnect(topic);
    this.frameCountPerTopic.delete(topic);

    // Remove topic from frames map
    const next = new Map(this.frames());
    next.delete(topic);
    this.frames.set(next);
  }

  private onTopicComplete(topic: string): void {
    // The server closed the stream (code 1001 or natural end).
    // Clean up our local subscription — MultiWebsocketService already deleted
    // its connection entry. Do NOT remove the topic from the workspace store;
    // the user still wants it selected. Re-connect so the stream resumes when
    // the backend comes back.
    this.subscriptions.delete(topic);
    this.frameCountPerTopic.delete(topic);

    const next = new Map(this.frames());
    next.delete(topic);
    this.frames.set(next);

    // Re-connect if the topic is still enabled in the store.
    const stillEnabled = this.workspaceStore
      .selectedTopics()
      .some(t => t.topic === topic && t.enabled);
    if (stillEnabled) {
      // Small delay so the backend has time to recover before we hammer it.
      setTimeout(() => this.connectTopic(topic), 1500);
    }
  }

  private onTopicError(topic: string): void {
    // A hard socket error occurred. MultiWebsocketService will attempt its own
    // reconnect cycle on the underlying socket, but our RxJS subscription is now
    // dead (error terminates an Observable). Clean up and re-subscribe so that
    // when the socket recovers, frames start flowing again.
    const sub = this.subscriptions.get(topic);
    sub?.unsubscribe();
    this.subscriptions.delete(topic);
    this.frameCountPerTopic.delete(topic);

    const next = new Map(this.frames());
    next.delete(topic);
    this.frames.set(next);

    // Re-connect if the topic is still enabled.
    const stillEnabled = this.workspaceStore
      .selectedTopics()
      .some(t => t.topic === topic && t.enabled);
    if (stillEnabled) {
      setTimeout(() => this.connectTopic(topic), 1500);
    }
  }

  private handleMessage(topic: string, data: any): void {
    // Increment frame counter for FPS tracking
    const count = this.frameCountPerTopic.get(topic) ?? 0;
    this.frameCountPerTopic.set(topic, count + 1);

    let payload: FramePayload | null = null;

    if (data instanceof ArrayBuffer) {
      payload = parseLidrFrame(data);
    } else {
      payload = this.parseJsonMessage(topic, data);
    }

    if (!payload) return;

    // Immutable Map update (signal requires a new reference to trigger)
    const next = new Map(this.frames());
    next.set(topic, payload);
    this.frames.set(next);

    // Update lidarTime if available
    if (payload.timestamp > 0) {
      const date = new Date(payload.timestamp * 1000);
      this.workspaceStore.set('lidarTime', date.toISOString().substr(11, 12));
    }

    // Update total point count (sum across all topics)
    let totalPoints = 0;
    this.frames().forEach(f => { totalPoints += f.count; });
    this.workspaceStore.set('pointCount', totalPoints);
  }

  private parseJsonMessage(topic: string, data: any): FramePayload | null {
    try {
      const raw = typeof data === 'string' ? JSON.parse(data) : data;
      const pointArrays = parseJsonPointCloud(raw);
      if (!pointArrays) return null;

      const flatArray = new Float32Array(pointArrays.length * 3);
      for (let i = 0; i < pointArrays.length; i++) {
        flatArray[i * 3]     = pointArrays[i][0];
        flatArray[i * 3 + 1] = pointArrays[i][1];
        flatArray[i * 3 + 2] = pointArrays[i][2];
      }

      return {
        timestamp: 0,
        count: pointArrays.length,
        points: flatArray,
      };
    } catch (e) {
      console.error(`[PointCloudData] JSON parse error for topic "${topic}":`, e);
      return null;
    }
  }

  private updateFps(): void {
    let total = 0;
    this.frameCountPerTopic.forEach(n => { total += n; });
    this.workspaceStore.set('fps', total);
    this.frameCountPerTopic.forEach((_, k) => this.frameCountPerTopic.set(k, 0));
  }
}
