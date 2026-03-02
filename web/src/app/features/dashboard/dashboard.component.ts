import { Component, OnInit, OnDestroy, effect, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynBadgeComponent } from '@synergy-design-system/angular';
import {
  MetricsStoreService,
  MetricsWebSocketService,
  MetricsApiService,
  ComponentPerfService,
} from '../../core/services';
import { DagOverviewPanelComponent } from './components/dag-overview-panel/dag-overview-panel.component';
import { DagNodeDetailPanelComponent } from './components/dag-node-detail-panel/dag-node-detail-panel.component';
import { WebsocketPanelComponent } from './components/websocket-panel/websocket-panel.component';
import { SystemPanelComponent } from './components/system-panel/system-panel.component';
import { RenderingPanelComponent } from './components/rendering-panel/rendering-panel.component';
import { firstValueFrom } from 'rxjs';

/**
 * Top-level smart component for /dashboard/performance
 * Reads MetricsStore signals and passes data down to dumb panel components
 * Handles initial REST snapshot load before WebSocket is ready
 */
@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    SynBadgeComponent,
    DagOverviewPanelComponent,
    DagNodeDetailPanelComponent,
    WebsocketPanelComponent,
    SystemPanelComponent,
    RenderingPanelComponent,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css',
})
export class DashboardComponent implements OnInit, OnDestroy {
  selectedNode: DagNodeMetrics | null = null;

  constructor(
    public metricsStore: MetricsStoreService,
    public metricsWebSocketService: MetricsWebSocketService,
    private metricsApiService: MetricsApiService,
    private componentPerfService: ComponentPerfService,
  ) {
    // Set up effect to capture metrics from PointCloudComponent when available
    // This will be called when workspace has a point cloud emitting metrics
    effect(() => {
      // This effect will run when any relevant signal changes
      // For now, just ensure the store is reactive to frontend metrics
      const frontendMetrics = this.metricsStore.frontendMetrics();
      if (frontendMetrics) {
        // Metrics are being captured and stored - effect is working
        console.log('[Dashboard] Frontend metrics available:', frontendMetrics.fps, 'FPS');
      }
    });
  }

  ngOnInit(): void {
    // Start metrics WebSocket connection
    this.metricsWebSocketService.connect();

    // Start component performance observing
    this.componentPerfService.startObserving();

    // Get initial snapshot via REST before first WebSocket push
    this.loadInitialSnapshot();
  }

  ngOnDestroy(): void {
    // Clean up connections and observers
    this.metricsWebSocketService.disconnect();
    this.componentPerfService.stopObserving();
  }

  onNodeSelected(node: DagNodeMetrics): void {
    this.selectedNode = node;
  }

  onCloseDetail(): void {
    this.selectedNode = null;
  }

  private async loadInitialSnapshot(): Promise<void> {
    try {
      const snapshot = await firstValueFrom(this.metricsApiService.getSnapshot());
      if (snapshot) {
        this.metricsStore.update(snapshot);
        console.log('[Dashboard] Loaded initial metrics snapshot');
      }
    } catch (error) {
      console.warn('[Dashboard] Failed to load initial snapshot:', error);
      // This is non-critical - WebSocket will provide data when ready
    }
  }
}
