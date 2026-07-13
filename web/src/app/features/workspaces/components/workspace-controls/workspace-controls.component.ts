import {ChangeDetectionStrategy, Component, computed, inject, output} from '@angular/core';
import {WorkspaceStoreService} from '@core/services';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {PointCloudDataService} from '@core/services/point-cloud-data.service';
import { WorkspaceTelemetryComponent } from '../workspace-telemetry/workspace-telemetry.component';

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
