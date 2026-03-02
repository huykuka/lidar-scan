import { Component, input, output, signal, computed } from '@angular/core';
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
  isLoading = input<boolean>(false);
  zoom = input<number>(1);

  groupedPlugins = computed(() => {
    const groups: { [key: string]: NodePlugin[] } = {};
    for (const plugin of this.plugins()) {
      const cat = plugin.category || 'other';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(plugin);
    }

    // Sort logic to put 'sensor' first, 'fusion' second, 'calibration' third, etc.
    const order = ['sensor', 'fusion', 'calibration', 'operation', 'other'];
    return Object.keys(groups)
      .sort((a, b) => {
        const indexA = order.indexOf(a);
        const indexB = order.indexOf(b);
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return a.localeCompare(b);
      })
      .map((key) => ({ category: key, plugins: groups[key] }));
  });

  onResetView = output<void>();
  onPluginDragStart = output<{ plugin: string; event: DragEvent }>();
  onPluginDragEnd = output<void>();
}
