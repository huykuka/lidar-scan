import {
  Component,
  OnInit,
  OnDestroy,
  inject,
  ViewChild,
  ChangeDetectorRef,
  effect,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NavigationService } from '../../core/services/navigation.service';
import { WebsocketService } from '../../core/services/websocket.service';
import { TopicApiService } from '../../core/services/api/topic-api.service';
import { WorkspaceStoreService } from '../../core/services/stores/workspace-store.service';
import { PointCloudComponent } from './components/point-cloud/point-cloud.component';
import { WorkspaceTelemetryComponent } from './components/workspace-telemetry/workspace-telemetry.component';
import { WorkspaceControlsComponent } from './components/workspace-controls/workspace-controls.component';
import { WorkspaceViewControlsComponent } from './components/workspace-view-controls/workspace-view-controls.component';
import { Subscription } from 'rxjs';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-workspaces',
  standalone: true,
  imports: [
    CommonModule,
    SynergyComponentsModule,
    PointCloudComponent,
    WorkspaceTelemetryComponent,
    WorkspaceControlsComponent,
    WorkspaceViewControlsComponent,
  ],
  templateUrl: './workspaces.component.html',
  styleUrl: './workspaces.component.css',
})
export class WorkspacesComponent implements OnInit, OnDestroy {
  @ViewChild('pointCloud') pointCloud!: PointCloudComponent;

  private navService = inject(NavigationService);
  private wsService = inject(WebsocketService);
  private topicApi = inject(TopicApiService);
  private workspaceStore = inject(WorkspaceStoreService);
  private cdr = inject(ChangeDetectorRef);

  protected pointSize = this.workspaceStore.pointSize;
  protected pointColor = this.workspaceStore.pointColor;
  protected showCockpit = this.workspaceStore.showCockpit;

  private wsSubscription?: Subscription;
  private frameCount = 0;
  private fpsUpdateInterval?: any;

  constructor() {
    // Reactively connect to WebSocket when topic changes in store
    effect(() => {
      const topic = this.workspaceStore.currentTopic();
      if (topic) {
        this.connectToTopic(topic);
      }
    });
  }

  ngOnInit() {
    this.navService.setHeadline('Workspaces');
    this.initWorkspace();

    this.fpsUpdateInterval = setInterval(() => {
      this.workspaceStore.set('fps', this.frameCount);
      this.frameCount = 0;
    }, 1000);
  }

  ngOnDestroy() {
    this.wsSubscription?.unsubscribe();
    this.wsService.disconnect();
    if (this.fpsUpdateInterval) {
      clearInterval(this.fpsUpdateInterval);
    }
  }

  private async initWorkspace() {
    const topics = await this.topicApi.getTopics();
    this.workspaceStore.set('topics', topics);

    // Initial topic selection if none exists
    if (topics.length > 0 && !this.workspaceStore.getValue('currentTopic')) {
      this.workspaceStore.set('currentTopic', topics[0]);
    }
  }

  private connectToTopic(topic: string) {
    this.workspaceStore.set('isConnected', false);
    this.wsService.connect(environment.wsUrl(topic));
    this.setupWsSubscription();
  }

  private setupWsSubscription() {
    this.wsSubscription?.unsubscribe();
    this.wsSubscription = this.wsService.messages$.subscribe((data) => {
      this.workspaceStore.set('isConnected', true);
      this.handleWsMessage(data);
    });
  }

  private async handleWsMessage(data: any) {
    this.frameCount++;
    if (data instanceof ArrayBuffer) {
      const payload = this.parseBinaryPointCloud(data);
      if (payload) {
        this.pointCloud.updatePoints(payload.points, payload.count);
        this.workspaceStore.set('pointCount', payload.count);
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
          this.pointCloud.updatePoints(flatArray, points.length);
          this.workspaceStore.set('pointCount', points.length);
        }
      } catch (e) {
        console.error('JSON parse error:', e);
      }
    }
    this.cdr.detectChanges();
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

  protected resetCamera() {
    this.pointCloud?.resetCamera();
  }

  protected clearPoints() {
    this.pointCloud?.clear();
    this.workspaceStore.set('pointCount', 0);
  }

  protected toggleCockpit() {
    this.workspaceStore.set('showCockpit', !this.showCockpit());
  }
}
