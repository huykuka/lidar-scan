import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, input, output } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

@Component({
  selector: 'app-preview-header',
  templateUrl: './preview-header.component.html',
  styleUrl: './preview-header.component.css',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [SynergyComponentsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PreviewHeaderComponent {
  readonly topicCount = input.required<number>();
  readonly showGizmos = input.required<boolean>();
  readonly isConnected = input.required<boolean>();

  readonly gizmoToggle = output<void>();
}
