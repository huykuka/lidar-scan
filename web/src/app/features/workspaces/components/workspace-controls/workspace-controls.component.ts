import { Component, inject, Output, EventEmitter, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { WorkspaceStoreService } from '../../../../core/services/stores/workspace-store.service';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { TopicApiService } from '../../../../core/services/api/topic-api.service';

@Component({
  selector: 'app-workspace-controls',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './workspace-controls.component.html',
  styleUrl: './workspace-controls.component.css',
})
export class WorkspaceControlsComponent {
  private store = inject(WorkspaceStoreService);
  private topicApi = inject(TopicApiService);

  protected topics = this.store.topics;
  protected currentTopic = this.store.currentTopic;
  protected selectedTopics = this.store.selectedTopics;
  protected isConnected = this.store.isConnected;
  protected pointSize = this.store.pointSize;

  @Output() actionTaken = new EventEmitter<void>();

  // Track newly selected topic in dropdown
  protected selectedNewTopic = '';

  // Computed list of available topics (excluding already selected ones)
  protected availableTopics = computed(() => {
    const all = this.topics();
    const selected = this.selectedTopics().map((t) => t.topic);
    return all.filter((t) => !selected.includes(t));
  });

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

  // Legacy method for backwards compatibility
  protected onLegacyTopicChange(event: any) {
    this.store.set('currentTopic', event.target.value);
    // Auto-add to selected topics if using legacy mode
    if (event.target.value) {
      this.store.addTopic(event.target.value);
    }
    this.actionTaken.emit();
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
}
