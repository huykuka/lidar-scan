import {ChangeDetectionStrategy, Component, input, output} from '@angular/core';
import {NgClass} from '@angular/common';
import {SynergyComponentsModule} from '@synergy-design-system/angular';

@Component({
  selector: 'app-node-editor-header',

  imports: [SynergyComponentsModule, NgClass],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './node-editor-header.component.html',
})
export class NodeEditorHeaderComponent {
  icon = input<string>('settings');
  iconColor = input<string>('text-syn-color-primary-600');
  title = input<string>('');
  description = input<string | undefined>(undefined);
  saveDisabled = input<boolean>(false);

  save = output<void>();
  cancel = output<void>();
}
