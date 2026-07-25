import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, input, output } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { PreviewTopic } from '../settings-preview-panel.component';

@Component({
  selector: 'app-preview-topic-list',
  templateUrl: './preview-topic-list.component.html',
  styleUrl: './preview-topic-list.component.css',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [SynergyComponentsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PreviewTopicListComponent {
  readonly topics = input.required<PreviewTopic[]>();

  readonly removeTopic = output<string>();
}
