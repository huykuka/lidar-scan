import { Component, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodePlugin } from '../../../../../core/models/node-plugin.model';

@Component({
  selector: 'app-flow-canvas-palette',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './flow-canvas-palette.component.html',
  styleUrl: './flow-canvas-palette.component.css',
})
export class FlowCanvasPaletteComponent {
  isCollapsed = signal<boolean>(false);
  plugins = input.required<NodePlugin[]>();
  zoom = input<number>(1);

  onAutoLayout = output<void>();
  onClearPositions = output<void>();
  onResetView = output<void>();
  onPluginDragStart = output<{ plugin: string; event: DragEvent }>();
  onPluginDragEnd = output<void>();
}
