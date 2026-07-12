import {
  ChangeDetectionStrategy,
  Component,
  computed,
  CUSTOM_ELEMENTS_SCHEMA,
  effect,
  inject,
  OnDestroy,
  signal,
} from '@angular/core';

import {Subscription} from 'rxjs';
import {MultiWebsocketService} from '@core/services/multi-websocket.service';
import {DEFAULT_TOPIC_COLORS} from '@core/services/stores/workspace-store.service';
import {ViewOrientation} from '@core/services/split-layout-store.service';
import { Pose, ZERO_POSE } from '@core/models';
import {environment} from '@env/environment';
import {NgtCanvas, NgtCanvasContent, NgtCanvasImpl} from 'angular-three/dom';
import {ThreedSceneGraphComponent, ViewportOverlayComponent} from '@shared/components';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import { CanvasEditStoreService } from '../../services/canvas-edit-store.service';
import { PreviewHeaderComponent } from './preview-header/preview-header.component';
import { PreviewTopicListComponent } from './preview-topic-list/preview-topic-list.component';
import { PreviewSceneComponent } from './preview-scene/preview-scene.component';
import * as THREE from 'three';

export interface PreviewTopic {
  nodeId: string;
  nodeName: string;
  topic: string;
  color: string;
  pointSize: number;
  pose: Pose;
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
    NgtCanvasImpl,
    NgtCanvasContent,
    SynergyComponentsModule,
    ViewportOverlayComponent,
    PreviewHeaderComponent,
    PreviewTopicListComponent,
    PreviewSceneComponent,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  providers: [MultiWebsocketService], // Own instance, isolated from workspace
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsPreviewPanelComponent implements OnDestroy {
  private readonly wsService = inject(MultiWebsocketService);
  private readonly canvasEditStore = inject(CanvasEditStoreService);

  /** Snap increments for pivot controls */
  readonly TRANSLATION_SNAP = 0.05; // 5cm
  readonly ROTATION_SNAP = 5; // 5 degrees

  /** Topics explicitly selected for preview via node context menu */
  readonly previewTopics = signal<PreviewTopic[]>([]);

  /** Latest frame data per topic (positions Float32Array + count) */
  readonly frames = signal<Map<string, { points: Float32Array; count: number }>>(new Map());

  readonly isConnected = signal(false);
  readonly showGrid = signal(true);
  readonly showGizmos = signal(false);
  readonly viewOrientation = signal<ViewOrientation>('perspective');
  readonly topicCount = computed(() => this.previewTopics().length);

  readonly MAX_POINTS = 250_000;
  private readonly DEG2RAD = Math.PI / 180;
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
        initialOffset: [t.pose.x, t.pose.y, t.pose.z] as [number, number, number],
        initialRotation: [
          t.pose.roll * this.DEG2RAD,
          t.pose.pitch * this.DEG2RAD,
          t.pose.yaw * this.DEG2RAD,
        ] as [number, number, number],
      };
    }),
  );

  constructor() {
    // Sync pivot matrices when backend node config changes (e.g. after Apply/Reload)
    effect(() => {
      const nodes = this.canvasEditStore.localNodes();
      const topics = this.previewTopics();
      if (!topics.length || this._isDragging) return;

      for (const t of topics) {
        const node = nodes.find((n) => n.id === t.nodeId);
        if (!node?.pose) continue;
        // Skip if this change came from our own drag
        if (this._draggedNodeIds.has(t.nodeId)) {
          this._draggedNodeIds.delete(t.nodeId);
          continue;
        }
        const currentPose = t.pose;
        if (
          node.pose.x !== currentPose.x || node.pose.y !== currentPose.y || node.pose.z !== currentPose.z ||
          node.pose.roll !== currentPose.roll || node.pose.pitch !== currentPose.pitch || node.pose.yaw !== currentPose.yaw
        ) {
          // External change detected — update without triggering via untracked
          this.syncPose(t.nodeId, node.pose);
        }
      }
    });
  }

  /** Add a node's topic to the preview and open its WebSocket connection. */
  addPreviewTopic(nodeId: string, nodeName: string, topic: string, initialPose?: Pose): void {
    const current = this.previewTopics();
    if (current.some((t) => t.topic === topic)) return;
    const colorIndex = current.length % DEFAULT_TOPIC_COLORS.length;
    this.previewTopics.set([
      ...current,
      {
        nodeId,
        nodeName,
        topic,
        color: DEFAULT_TOPIC_COLORS[colorIndex],
        pointSize: 2,
        pose: initialPose ? { ...initialPose } : { ...ZERO_POSE },
      },
    ]);
    this._connectTopic(topic);
  }

  /** Sync pose from external source (e.g. after backend save/reload). Updates the gizmo position. */
  syncPose(nodeId: string, pose: Pose): void {
    const topic = this.previewTopics().find((t) => t.nodeId === nodeId)?.topic;
    if (!topic) return;
    this.previewTopics.update((topics) =>
      topics.map((t) => (t.nodeId === nodeId ? { ...t, pose } : t)),
    );
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

    // 2. Release all Float32Array buffers
    this.staticBuffers.clear();

    // 3. Clear frame data references
    this.frames.set(new Map());

    // 4. Clear topic list
    this.previewTopics.set([]);
  }

  // -- Private WebSocket management --

  /** Called when a pivot control is dragged; extracts pose from the local matrix and syncs to store. */
  onPivotDrag(topic: string, event: any): void {
    this._isDragging = true;
    // NgtsPivotControls (dragged) emits { l: Matrix4, deltaL: Matrix4, w: Matrix4, deltaW: Matrix4 }
    const matrix = event.l as THREE.Matrix4;
    if (!matrix || !matrix.elements) return;

    const position = new THREE.Vector3();
    const quaternion = new THREE.Quaternion();
    const scale = new THREE.Vector3();
    matrix.decompose(position, quaternion, scale);

    const euler = new THREE.Euler().setFromQuaternion(quaternion, 'XYZ');
    const RAD2DEG = 180 / Math.PI;
    const SNAP_T = this.TRANSLATION_SNAP;
    const SNAP_R = this.ROTATION_SNAP;

    const snap = (v: number, step: number) => Math.round(v / step) * step;

    this._lastDragPose = {
      x: snap(position.x, SNAP_T),
      y: snap(position.y, SNAP_T),
      z: snap(position.z, SNAP_T),
      roll: snap(euler.x * RAD2DEG, SNAP_R),
      pitch: snap(euler.y * RAD2DEG, SNAP_R),
      yaw: snap(euler.z * RAD2DEG, SNAP_R),
    };

    this._lastDragTopic = topic;
  }

  /** Called when a pivot control drag ends; commits the pose to the store. */
  onPivotDragEnd(topic: string): void {
    const pose = this._lastDragPose;
    if (!pose || this._lastDragTopic !== topic) return;

    // Sync pose to the flow-canvas node store (marks isDirty, enables Apply button)
    const previewTopic = this.previewTopics().find((t) => t.topic === topic);
    if (previewTopic) {
      this._draggedNodeIds.add(previewTopic.nodeId);
      console.log(`Syncing pose for node ${previewTopic.nodeId}:`, pose);
      this.canvasEditStore.updateNode(previewTopic.nodeId, { pose });
    }

    this._lastDragPose = null;
    this._lastDragTopic = null;
    this._isDragging = false;
  }

  private _lastDragPose: Pose | null = null;
  private _lastDragTopic: string | null = null;
  private _isDragging = false;
  /** Node IDs whose pose was changed by drag — skip sync effect for these */
  private _draggedNodeIds = new Set<string>();

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
