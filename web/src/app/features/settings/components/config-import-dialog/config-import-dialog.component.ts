import { Component, input, output, model } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { ConfigValidationResponse } from '../../../../core/models/config.model';

@Component({
  selector: 'app-config-import-dialog',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './config-import-dialog.component.html',
})
export class ConfigImportDialogComponent {
  // Inputs
  open = input<boolean>(false);
  validationResult = input<ConfigValidationResponse | null>(null);
  isImporting = input<boolean>(false);
  
  // Two-way binding for merge mode
  mergeMode = model<boolean>(false);

  // Outputs
  cancel = output<void>();
  confirm = output<void>();
  requestClose = output<void>();
}
