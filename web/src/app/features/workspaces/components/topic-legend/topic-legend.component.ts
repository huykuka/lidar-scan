import {ChangeDetectionStrategy, Component, computed, inject, signal} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {WorkspaceStoreService} from '@core/services/stores/workspace-store.service';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {buildTopicStatuses} from '../../topic-status.util';
import {PointCloudDataService} from '@core/services/point-cloud-data.service';

/**
 * Small-screen HUD for the workspace 3D viewer: lists the visible topics with
 * the color they are rendered in. Collapsible so it never hides the scene.
 * Hidden on desktop, where the settings panel already shows this.
 */
@Component({
  selector: 'app-topic-legend',
  imports: [SynergyComponentsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './topic-legend.component.html',
  styleUrl: './topic-legend.component.css',
})
export class TopicLegendComponent {
  private store = inject(WorkspaceStoreService);
  private dataService = inject(PointCloudDataService);
  private nodeStore = inject(NodeStoreService);

  protected expanded = signal(true);

  protected items = computed(() => {
    const frames = this.dataService.frames();
    const enabled = this.store.selectedTopics().filter((t) => t.enabled);
    const statuses = buildTopicStatuses(
      Array.from(this.nodeStore.nodeStatusMap().values()),
      enabled.map((t) => t.topic),
    );
    return enabled.map((t) => ({
        status: statuses.get(t.topic) ?? null,
        topic: t.topic,
        // Drop the trailing node-id hash (e.g. `_1bec54a0`) for readability
        label: t.topic.replace(/_[0-9a-f]{8}$/i, ''),
        color: t.color,
        live: (frames.get(t.topic)?.count ?? 0) > 0,
      }));
  });

}
