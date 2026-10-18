import {ChangeDetectionStrategy, Component, computed, inject, output} from '@angular/core';
import {WorkspaceStoreService} from '@core/services';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {PointCloudDataService} from '@core/services/point-cloud-data.service';
import { WorkspaceTelemetryComponent } from '../workspace-telemetry/workspace-telemetry.component';

interface TopicStatusView {
  text: string | null;
  color: string;
  cycle: string | null;
}

@Component({
  selector: 'app-workspace-controls',
  imports: [SynergyComponentsModule, WorkspaceTelemetryComponent],
  templateUrl: './workspace-controls.component.html',
  styleUrl: './workspace-controls.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceControlsComponent {
  readonly actionTaken = output<void>();
  protected selectedNewTopic = '';
  protected availableTopics = computed(() => {
    const selected = this.selectedTopics().map((t: any) => t.topic);
    return this.topics().filter((t: any) => !selected.includes(t.topic));
  });

  /**
   * Groups availableTopics by their node category (sensor / operation / fusion / other).
   * Returns an array of { label, topics } ordered by label.
   */
  protected groupedAvailableTopics = computed(() => {
    const map = new Map<string, string[]>();
    for (const info of this.availableTopics()) {
      const label = info.category || 'other';
      if (!map.has(label)) map.set(label, []);
      map.get(label)!.push(info.topic);
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([label, topics]) => ({ label, topics }));
  });
  /** Maps node category to a Synergy icon name. */
  protected readonly categoryIcon: Record<string, string> = {
    sensor: 'sensors',
    operation: 'filter_alt',
    fusion: 'mediation',
    other: 'device_unknown',
  };

  protected getCategoryIcon(category: string): string {
    return this.categoryIcon[category] ?? this.categoryIcon['other'];
  }
  private nodeStore = inject(NodeStoreService);

  /** Live status per topic. Topics are named `{node_name}_{node_id[:8]}`. */
  protected topicStatuses = computed(() => {
    const statuses = Array.from(this.nodeStore.nodeStatusMap().values());
    const result = new Map<string, TopicStatusView>();
    for (const {topic} of this.selectedTopics()) {
      const suffix = topic.slice(topic.lastIndexOf('_') + 1);
      const status = statuses.find((s) => s.node_id.startsWith(suffix));
      if (!status) continue;
      const app = status.application_state;
      const ms = status.cycle_time_ms;
      const cycle =
        ms === null || ms === undefined
          ? null
          : ms >= 1000
            ? `${(ms / 1000).toFixed(1)}s`
            : `${ms.toFixed(ms >= 10 ? 0 : 1)}ms`;
      if (!app && !cycle) continue;
      result.set(topic, {
        text: app ? `${app.label}: ${app.value}` : null,
        color: this.badgeColors[app?.color ?? 'gray'] ?? this.badgeColors['gray'],
        cycle,
      });
    }
    return result;
  });

  private readonly badgeColors: Record<string, string> = {
    green: '#16a34a',
    blue: '#2563eb',
    orange: '#d97706',
    red: '#dc2626',
    gray: '#6b7280',
  };

  private dataService = inject(PointCloudDataService);
  private store = inject(WorkspaceStoreService);
  protected topics = this.store.topics;
  protected selectedTopics = this.store.selectedTopics;
  protected isConnected = this.dataService.isConnected;

  protected onTopicSelect(event: any) {
    const topic = event.target.value;
    if (!topic) return;

    // Immediately add the selected topic
    this.store.addTopic(topic);

    // Reset the dropdown to empty state
    this.selectedNewTopic = '';
    this.actionTaken.emit();
  }

  protected removeTopic(topic: string) {
    this.store.removeTopic(topic);
    this.actionTaken.emit();
  }

  protected onTopicColorChange(topic: string, event: any) {
    this.store.updateTopicColor(topic, event.target.value);
  }

  protected onTopicPointSizeChange(topic: string, event: any) {
    this.store.updateTopicPointSize(topic, parseFloat(event.target.value));
  }
}
