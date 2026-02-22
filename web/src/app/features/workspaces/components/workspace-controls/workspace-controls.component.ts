import { Component, inject, Output, EventEmitter } from '@angular/core';
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
  protected isConnected = this.store.isConnected;
  protected pointSize = this.store.pointSize;
  protected pointColor = this.store.pointColor;

  @Output() actionTaken = new EventEmitter<void>();

  protected onTopicChange(event: any) {
    this.store.set('currentTopic', event.target.value);
    this.actionTaken.emit();
  }

  protected onCapturePcd() {
    const topic = this.currentTopic();
    if (topic) {
      this.topicApi.downloadPcd(topic);
    }
    this.actionTaken.emit();
  }

  protected onPointSizeChange(event: any) {
    this.store.set('pointSize', parseFloat(event.target.value));
  }

  protected onPointColorChange(event: any) {
    this.store.set('pointColor', event.target.value);
  }
}
