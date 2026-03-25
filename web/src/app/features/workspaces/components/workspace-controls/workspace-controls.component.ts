import {Component, computed, inject, output} from '@angular/core';
import {DecimalPipe} from '@angular/common';
import {TopicApiService, WorkspaceStoreService} from '@core/services';
import {SynergyComponentsModule} from '@synergy-design-system/angular';

@Component({
  selector: 'app-workspace-controls',
  imports: [SynergyComponentsModule, DecimalPipe],
  templateUrl: './workspace-controls.component.html',
  styleUrl: './workspace-controls.component.css',
})
export class WorkspaceControlsComponent {
  readonly actionTaken = output<void>();
  // Track newly selected topic in dropdown
  protected selectedNewTopic = '';
  // Computed list of available topics (excluding already selected ones)
  protected availableTopics = computed(() => {
    const all = this.topics();
    const selected = this.selectedTopics().map((t) => t.topic);
    return all.filter((t) => !selected.includes(t));
  });
  private store = inject(WorkspaceStoreService);
  protected topics = this.store.topics;
  protected selectedTopics = this.store.selectedTopics;
  protected isConnected = this.store.isConnected;
  protected pointSize = this.store.pointSize;
  protected backgroundColor = this.store.backgroundColor;
  private topicApi = inject(TopicApiService);

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

  protected toggleTopicEnabled(topic: string) {
    this.store.toggleTopicEnabled(topic);
    this.actionTaken.emit();
  }

  protected onTopicColorChange(topic: string, event: any) {
    this.store.updateTopicColor(topic, event.target.value);
  }

  protected onCapturePcd(topic: string) {
    if (topic) {
      this.topicApi.downloadPcd(topic);
    }
    this.actionTaken.emit();
  }

  protected onPointSizeChange(event: any) {
    this.store.set('pointSize', parseFloat(event.target.value));
  }

  protected onBackgroundColorChange(event: any) {
    this.store.set('backgroundColor', event.target.value);
  }
}
