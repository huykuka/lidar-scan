import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { FusionConfig } from '../../../../core/models/fusion.model';
import { NodesStatusResponse } from '../../../../core/services/api/nodes-api.service';

@Component({
  selector: 'app-fusion-card',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './fusion-card.component.html',
})
export class FusionCardComponent {
  // Inputs
  fusion = input.required<FusionConfig>();
  isLoading = input<boolean>(false);
  nodeStatus = input<NodesStatusResponse['fusions'][0] | null>(null);
  sensorsLabel = input<string>('');

  // Outputs
  toggleEnabled = output<{ fusion: FusionConfig; enabled: boolean }>();
  edit = output<FusionConfig>();
  delete = output<string>();
}
