import {Component, computed, effect, inject, OnDestroy, OnInit, signal} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NavigationService} from '@core/services/navigation.service';
import {TopicApiService} from '@core/services/api/topic-api.service';
import {WorkspaceStoreService} from '@core/services/stores/workspace-store.service';
import {NodeStatusService} from '@core/services/node-status.service';
import {SplitLayoutStoreService} from '@core/services/split-layout-store.service';
import {
  WorkspaceTelemetryComponent
} from '@features/workspaces/components/workspace-telemetry/workspace-telemetry.component';
import {
  WorkspaceControlsComponent
} from '@features/workspaces/components/workspace-controls/workspace-controls.component';
import {
  SplitPaneContainerComponent
} from '@features/workspaces/components/split-pane/split-pane-container/split-pane-container.component';
import {ViewToolbarComponent} from '@features/workspaces/components/view-toolbar/view-toolbar.component';

@Component({
  selector: 'app-workspaces',
  imports: [
    SynergyComponentsModule,
    WorkspaceTelemetryComponent,
    WorkspaceControlsComponent,
    SplitPaneContainerComponent,
    ViewToolbarComponent,
  ],
  templateUrl: './workspaces.component.html',
  styleUrl: './workspaces.component.css',
})
export class WorkspacesComponent implements OnInit, OnDestroy {
  private navService = inject(NavigationService);
  private topicApi = inject(TopicApiService);
  private workspaceStore = inject(WorkspaceStoreService);
  private statusWs = inject(NodeStatusService);
  private splitLayout = inject(SplitLayoutStoreService);

  protected showCockpit = this.workspaceStore.showCockpit;

  /** Hide HUD and cockpit controls when more than one pane is active */
  protected isSinglePane = computed(() => this.splitLayout.paneCount() <= 1);

  // ── FE-11: Responsive narrow-screen guard ──────────────────────────────────
  protected isNarrowScreen = signal(window.innerWidth < 1024);
  private _narrowMql = window.matchMedia('(max-width: 1023px)');
  private _narrowListener = (e: MediaQueryListEvent) => this.isNarrowScreen.set(e.matches);

  private lastNodeIds = '';

  constructor() {
    // Register responsive breakpoint listener
    this._narrowMql.addEventListener('change', this._narrowListener);

    // React to NodeStatus changes: refresh available topics when nodes change
    effect(() => {
      const status = this.statusWs.status();
      if (!status) return;

      const nodeIds = status.nodes.map((n) => n.node_id).sort().join(',');
      if (nodeIds === this.lastNodeIds) return;

      this.lastNodeIds = nodeIds;
      this.refreshTopics();
    });
  }

  ngOnInit() {
    this.navService.setPageConfig({
      title: 'Workspaces',
      subtitle: 'Real-time 3D visualization of point cloud streams',
    });
    this.refreshTopics();
  }

  ngOnDestroy() {
    this.workspaceStore.set('showCockpit', false);
    this._narrowMql.removeEventListener('change', this._narrowListener);
  }

  /** Only allow closing via the close button — block overlay click and Esc. */
  protected onDrawerRequestClose(event: CustomEvent) {
    if (event.detail.source !== 'close-button') {
      event.preventDefault();
      return
    }
    this.workspaceStore.set('showCockpit', false);

  }

  protected toggleCockpit() {
    this.workspaceStore.set('showCockpit', !this.showCockpit());
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
}
