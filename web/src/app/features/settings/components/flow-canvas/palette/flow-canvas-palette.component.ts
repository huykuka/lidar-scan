import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  input,
  signal,
  untracked,
} from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { FExternalItem, FExternalItemPlaceholder } from '@foblex/flow';
import { NodePlugin } from '@core/models';

@Component({
  selector: 'app-flow-canvas-palette',
  imports: [SynergyComponentsModule, FExternalItem],
  templateUrl: './flow-canvas-palette.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './flow-canvas-palette.component.css',
})
export class FlowCanvasPaletteComponent {
  isCollapsed = signal<boolean>(false);
  plugins = input.required<NodePlugin[]>();
  isLoading = input<boolean>(false);
  searchQuery = signal<string>('');

  constructor() {
    effect(() => {
      const newCats = this.plugins().map((p) => p.category || 'other');
      untracked(() => this.expandedCategories.update((set) => new Set([...set, ...newCats])));
    });
  }

  filteredPlugins = computed(() => {
    const query = this.searchQuery().toLowerCase().trim();
    if (!query) return this.plugins();
    return this.plugins().filter(
      (p) =>
        p.displayName.toLowerCase().includes(query) ||
        p.type.toLowerCase().includes(query) ||
        p.category?.toLowerCase().includes(query),
    );
  });

  expandedCategories = signal<Set<string>>(new Set());

  groupedPlugins = computed(() => {
    const groups: { [key: string]: NodePlugin[] } = {};
    for (const plugin of this.filteredPlugins()) {
      const cat = plugin.category || 'other';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(plugin);
    }
    return Object.keys(groups)
      .sort()
      .map((key) => ({ category: key, plugins: groups[key] }));
  });

  onSearch(event: Event) {
    this.searchQuery.set((event.target as HTMLInputElement).value);
  }

  toggleCategory(cat: string) {
    this.expandedCategories.update((set) => {
      const next = new Set(set);
      next.has(cat) ? next.delete(cat) : next.add(cat);
      return next;
    });
  }

  isExpanded(cat: string): boolean {
    return this.expandedCategories().has(cat) || this.searchQuery() !== '';
  }
}
