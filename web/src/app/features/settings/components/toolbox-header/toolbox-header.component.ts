import { Component, output, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

@Component({
  selector: 'app-toolbox-header',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './toolbox-header.component.html',
})
export class ToolboxHeaderComponent {
  // Inputs
  isExporting = input<boolean>(false);
  isImporting = input<boolean>(false);

  // Outputs
  exportConfig = output<void>();
  importConfig = output<void>();
  reloadConfig = output<void>();
  addLidar = output<void>();
  addFusion = output<void>();
  dragStart = output<{ event: DragEvent; type: 'lidar' | 'fusion' }>();

  onDragStart(event: DragEvent, type: 'lidar' | 'fusion') {
    if (event.dataTransfer) {
      event.dataTransfer.setData('componentType', type);
      event.dataTransfer.effectAllowed = 'copy';
    }
    this.dragStart.emit({ event, type });
  }
}
