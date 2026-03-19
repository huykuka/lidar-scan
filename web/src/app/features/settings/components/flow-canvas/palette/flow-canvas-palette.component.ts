import {Component, computed, CUSTOM_ELEMENTS_SCHEMA, effect, input, output, signal, untracked} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NodePlugin} from '@core/models';

@Component({
  selector: 'app-flow-canvas-palette',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './flow-canvas-palette.component.html',
  styleUrl: './flow-canvas-palette.component.css',
})
export class FlowCanvasPaletteComponent {
  isCollapsed = signal<boolean>(false);
  plugins = input.required<NodePlugin[]>();
  isLoading = input<boolean>(false);
  zoom = input<number>(1);
  searchQuery = signal<string>('');

  constructor() {
    effect(() => {
      const allPlugs = this.plugins();
      untracked(() => {
        const cats = new Set(this.expandedCategories());
        allPlugs.forEach(p => {
          const cat = p.category || 'other';
          if (!cats.has(cat)) {
            cats.add(cat);
          }
        });
        this.expandedCategories.set(cats);
      });
    });
  }

  filteredPlugins = computed(() => {
    const query = this.searchQuery().toLowerCase().trim();
    if (!query) return this.plugins();

    return this.plugins().filter(p =>
      p.displayName.toLowerCase().includes(query) ||
      p.type.toLowerCase().includes(query) ||
      p.category?.toLowerCase().includes(query)
    );
  });

  expandedCategories = signal<Set<string>>(new Set());

  groupedPlugins = computed(() => {
    const groups: { [key: string]: NodePlugin[] } = {};
    const currentPlugins = this.filteredPlugins();
    
    for (const plugin of currentPlugins) {
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
      .map((key) => ({category: key, plugins: groups[key]}));
  });

  onResetView = output<void>();
  onPluginDragStart = output<{ plugin: string; event: DragEvent }>();
  onPluginDragEnd = output<void>();

  onSearch(event: any) {
    this.searchQuery.set(event.target.value);
  }

  toggleCategory(cat: string) {
    this.expandedCategories.update(set => {
      const newSet = new Set(set);
      if (newSet.has(cat)) newSet.delete(cat);
      else newSet.add(cat);
      return newSet;
    });
  }

  isExpanded(cat: string): boolean {
    return this.expandedCategories().has(cat) || this.searchQuery() !== '';
  }
}
