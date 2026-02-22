import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarConfig } from '../../../../core/models/lidar.model';
import { NodesStatusResponse } from '../../../../core/services/api/nodes-api.service';

@Component({
  selector: 'app-lidar-card',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './lidar-card.component.html',
})
export class LidarCardComponent {
  // Inputs
  lidar = input.required<LidarConfig>();
  isLoading = input<boolean>(false);
  nodeStatus = input<NodesStatusResponse['lidars'][0] | null>(null);

  // Outputs
  toggleEnabled = output<{ lidar: LidarConfig; enabled: boolean }>();
  edit = output<LidarConfig>();
  delete = output<string>();

  protected getTopic(): string {
    const l = this.lidar();
    return l.processed_topic || l.raw_topic || (l.topic_prefix ? `${l.topic_prefix}_raw_points` : '');
  }
}
