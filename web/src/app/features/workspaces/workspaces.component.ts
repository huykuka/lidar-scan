import {AfterViewInit, Component, effect, inject, OnDestroy, OnInit, viewChild} from '@angular/core';
import {NgClass} from '@angular/common';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NavigationService} from '@core/services/navigation.service';
import {MultiWebsocketService} from '@core/services/multi-websocket.service';
import {TopicApiService} from '@core/services/api/topic-api.service';
import {WorkspaceStoreService} from '@core/services/stores/workspace-store.service';
import {StatusWebSocketService} from '@core/services/status-websocket.service';
import {PointCloudComponent} from '@features/workspaces/components/point-cloud/point-cloud.component';
import {
  WorkspaceTelemetryComponent
} from '@features/workspaces/components/workspace-telemetry/workspace-telemetry.component';
import {
  WorkspaceControlsComponent
} from '@features/workspaces/components/workspace-controls/workspace-controls.component';
import {
  WorkspaceViewControlsComponent
} from '@features/workspaces/components/workspace-view-controls/workspace-view-controls.component';
import {Subscription} from 'rxjs';
import {environment} from '@env/environment';

@Component({
  selector: 'app-workspaces',
  imports: [
    SynergyComponentsModule,
    PointCloudComponent,
    WorkspaceTelemetryComponent,
    WorkspaceControlsComponent,
    WorkspaceViewControlsComponent,
    NgClass
],
  templateUrl: './workspaces.component.html',
  styleUrl: './workspaces.component.css',
})
export class WorkspacesComponent implements OnInit, AfterViewInit, OnDestroy {
  readonly pointCloud = viewChild.required<PointCloudComponent>('pointCloud');

  private navService = inject(NavigationService);
  private wsService = inject(MultiWebsocketService);
  private topicApi = inject(TopicApiService);
  private workspaceStore = inject(WorkspaceStoreService);
  private statusWs = inject(StatusWebSocketService);
  protected pointSize = this.workspaceStore.pointSize;
  protected showCockpit = this.workspaceStore.showCockpit;
  protected showGrid = this.workspaceStore.showGrid;
  protected showAxes = this.workspaceStore.showAxes;
  protected backgroundColor = this.workspaceStore.backgroundColor;
  private wsSubscriptions = new Map<string, Subscription>();
  private frameCountPerTopic = new Map<string, number>();
  private fpsUpdateInterval?: any;
  private viewInitialized = false;
  private lastNodeIds = '';
  private lastVisibilityKey = '';

  constructor() {
    effect(() => {
      const selectedTopics = this.workspaceStore.selectedTopics();
      if (this.viewInitialized) {
        this.syncWebSocketConnections(selectedTopics);
      }
    });

    effect(() => {
      const status = this.statusWs.status();
      if (!status) return;
      
      // Use node_id from new NodeStatusUpdate schema
      const nodeIds = status.nodes.map(n => n.node_id).sort().join(',');
      // Note: visibility is in NodeConfig, not in status. This effect only tracks node existence changes.
      // Visibility changes should be tracked separately if needed via nodeStore.nodes()
      
      if (nodeIds === this.lastNodeIds) return;
      
      this.lastNodeIds = nodeIds;
      this.lastVisibilityKey = nodeIds; // Simplified - just track nodes, not visibility
      this.refreshTopics();
    });
  }

  ngOnInit() {
    this.navService.setPageConfig({
      title: 'Workspaces',
      subtitle: 'Real-time 3D visualization of point cloud streams',
    });
    this.initWorkspace();

    this.fpsUpdateInterval = setInterval(() => {
      // Calculate total FPS across all topics
      let totalFrames = 0;
      this.frameCountPerTopic.forEach((count) => {
        totalFrames += count;
      });
      this.workspaceStore.set('fps', totalFrames);
      this.frameCountPerTopic.clear();
    }, 1000);
  }

  ngAfterViewInit() {
    // Mark view as initialized
    this.viewInitialized = true;

    // Trigger initial sync now that pointCloud component is available
    const selectedTopics = this.workspaceStore.selectedTopics();
    this.syncWebSocketConnections(selectedTopics);
  }

  ngOnDestroy() {
    this.viewInitialized = false;
    this.wsSubscriptions.forEach((sub) => sub.unsubscribe());
    this.wsSubscriptions.clear();
    this.wsService.disconnectAll();
    if (this.fpsUpdateInterval) {
      clearInterval(this.fpsUpdateInterval);
    }
  }

  protected resetCamera() {
    this.pointCloud()?.resetCamera();
  }

  protected setTopView() {
    this.pointCloud()?.setTopView();
  }

  protected setFrontView() {
    this.pointCloud()?.setFrontView();
  }

  protected setSideView() {
    this.pointCloud()?.setSideView();
  }

  protected setIsometricView() {
    this.pointCloud()?.setIsometricView();
  }

  protected fitToPoints() {
    this.pointCloud()?.fitToPoints();
  }

  protected captureScreenshot() {
    const topic = this.workspaceStore.currentTopic();
    const safeTopic = (topic || 'workspace').replace(/[^A-Za-z0-9_-]+/g, '_');
    this.pointCloud()?.capturePng(`${safeTopic}.png`);
  }

  protected clearPoints() {
    this.pointCloud()?.clear();
    this.workspaceStore.set('pointCount', 0);
  }

  protected toggleGrid() {
    this.workspaceStore.set('showGrid', !this.showGrid());
  }

  protected toggleAxes() {
    this.workspaceStore.set('showAxes', !this.showAxes());
  }

  protected toggleCockpit() {
    this.workspaceStore.set('showCockpit', !this.showCockpit());
  }

  protected closeCockpit() {
    this.workspaceStore.set('showCockpit', false);
  }

  private async initWorkspace() {
    const topics = await this.topicApi.getTopics();
    this.workspaceStore.set('topics', topics);

    // Validate and clean up persisted topics
    const selectedTopics = this.workspaceStore.getValue('selectedTopics');
    const validSelectedTopics = selectedTopics.filter((st) => topics.includes(st.topic));

    // Update store with only valid topics
    if (validSelectedTopics.length !== selectedTopics.length) {
      this.workspaceStore.set('selectedTopics', validSelectedTopics);
    }

    // Auto-select first topic if no valid topics are selected
    if (topics.length > 0 && validSelectedTopics.length === 0) {
      this.workspaceStore.addTopic(topics[0]);
    }
  }

  private async refreshTopics() {
    const topics = await this.topicApi.getTopics();
    this.workspaceStore.set('topics', topics);

    const selectedTopics = this.workspaceStore.getValue('selectedTopics');
    const validSelectedTopics = selectedTopics.filter((st) => topics.includes(st.topic));
    if (validSelectedTopics.length !== selectedTopics.length) {
      this.workspaceStore.set('selectedTopics', validSelectedTopics);
    }
  }

  /**
   * Sync WebSocket connections with selected topics
   * Connect to enabled topics, disconnect from disabled or removed topics
   */
  private syncWebSocketConnections(
    selectedTopics: Array<{ topic: string; color: string; enabled: boolean }>,
  ) {
    const enabledTopics = selectedTopics.filter((t) => t.enabled);
    const enabledTopicNames = new Set(enabledTopics.map((t) => t.topic));

    // Disconnect and remove point clouds for topics that are no longer enabled (or were removed)
    this.wsSubscriptions.forEach((_, topic) => {
      if (!enabledTopicNames.has(topic)) {
        this.disconnectFromTopic(topic);
        this.pointCloud()?.removePointCloud(topic);
      }
    });

    // Connect to newly enabled topics and update colors
    enabledTopics.forEach(({topic, color}) => {
      this.pointCloud()?.addOrUpdatePointCloud(topic, color);
      if (!this.wsSubscriptions.has(topic)) {
        this.connectToTopic(topic);
      }
    });

    // Safety: Remove point clouds for disabled topics that are still in selectedTopics
    selectedTopics
      .filter((t) => !t.enabled)
      .forEach(({topic}) => {
        this.pointCloud()?.removePointCloud(topic);
      });

    // Update connection status
    const isAnyConnected = enabledTopics.length > 0;
    this.workspaceStore.set('isConnected', isAnyConnected);
  }

  private connectToTopic(topic: string) {
    if (this.wsSubscriptions.has(topic)) return;

    const url = environment.wsUrl(topic);
    const subscription = this.wsService.connect(topic, url).subscribe({
      next: (data) => this.handleWsMessage(topic, data),
      complete: () => {
        this.wsSubscriptions.delete(topic);
        this.frameCountPerTopic.delete(topic);
        this.pointCloud()?.removePointCloud(topic);
        this.workspaceStore.removeTopic(topic);
      },
      error: () => {
        this.wsSubscriptions.delete(topic);
        this.frameCountPerTopic.delete(topic);
      },
    });

    this.wsSubscriptions.set(topic, subscription);
    this.frameCountPerTopic.set(topic, 0);
  }

  private disconnectFromTopic(topic: string) {
    const subscription = this.wsSubscriptions.get(topic);
    if (subscription) {
      subscription.unsubscribe();
      this.wsSubscriptions.delete(topic);
    }

    this.wsService.disconnect(topic);
    this.frameCountPerTopic.delete(topic);
  }

  private async handleWsMessage(topic: string, data: any) {
    // Increment frame count for this topic
    const currentCount = this.frameCountPerTopic.get(topic) || 0;
    this.frameCountPerTopic.set(topic, currentCount + 1);

    if (data instanceof ArrayBuffer) {
      const payload = this.parseBinaryPointCloud(data);
      if (payload) {
        this.pointCloud()?.updatePointsForTopic(topic, payload.points, payload.count);

        // Update total point count
        const totalPoints = this.pointCloud()?.getTotalPointCount() || 0;
        this.workspaceStore.set('pointCount', totalPoints);

        if (payload.timestamp > 0) {
          const date = new Date(payload.timestamp * 1000);
          this.workspaceStore.set('lidarTime', date.toISOString().substr(11, 12));
        }
      }
    } else {
      try {
        const payload = JSON.parse(data);
        const points = this.extractPointsFromJson(payload);
        if (points) {
          const flatArray = new Float32Array(points.length * 3);
          for (let i = 0; i < points.length; i++) {
            flatArray[i * 3] = points[i][0];
            flatArray[i * 3 + 1] = points[i][1];
            flatArray[i * 3 + 2] = points[i][2];
          }
          this.pointCloud()?.updatePointsForTopic(topic, flatArray, points.length);

          // Update total point count
          const totalPoints = this.pointCloud()?.getTotalPointCount() || 0;
          this.workspaceStore.set('pointCount', totalPoints);
        }
      } catch (e) {
        console.error('JSON parse error:', e);
      }
    }
  }

  private parseBinaryPointCloud(buffer: ArrayBuffer) {
    const view = new DataView(buffer);
    const magic = String.fromCharCode(
      view.getUint8(0),
      view.getUint8(1),
      view.getUint8(2),
      view.getUint8(3),
    );
    if (magic !== 'LIDR') return null;
    return {
      timestamp: view.getFloat64(8, true),
      count: view.getUint32(16, true),
      points: new Float32Array(buffer.slice(20)),
    };
  }

  private extractPointsFromJson(payload: any): any[] | null {
    if (Array.isArray(payload)) return payload;
    if (payload.points && Array.isArray(payload.points)) return payload.points;
    if (payload.data && Array.isArray(payload.data)) return payload.data;
    if (payload.data?.points && Array.isArray(payload.data.points)) return payload.data.points;
    return null;
  }
}
