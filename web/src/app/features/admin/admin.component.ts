import {Component, computed, inject, OnInit, signal, ChangeDetectionStrategy} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NavigationService, ToastService} from '@core/services';
import {AdminApiService, NodeTypeRecord} from '@core/services/api/admin-api.service';

@Component({
  selector: 'app-admin',
  imports: [SynergyComponentsModule],
  templateUrl: './admin.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './admin.component.css',
})
export class AdminComponent implements OnInit {
  private navService = inject(NavigationService);
  private adminApi = inject(AdminApiService);
  private toast = inject(ToastService);

  protected nodeTypes = signal<NodeTypeRecord[]>([]);
  protected isLoading = signal(true);
  protected togglingType = signal<string | null>(null);
  protected searchQuery = signal('');
  protected filterCategory = signal<string | null>(null);

  protected categories = computed(() => {
    const cats = new Set(this.nodeTypes().map((n) => n.category));
    return Array.from(cats).sort();
  });

  protected filteredNodeTypes = computed(() => {
    let items = this.nodeTypes();
    const query = this.searchQuery().toLowerCase().trim();
    const cat = this.filterCategory();

    if (query) {
      items = items.filter(
        (n) =>
          n.display_name.toLowerCase().includes(query) ||
          n.type.toLowerCase().includes(query) ||
          n.category.toLowerCase().includes(query) ||
          n.description.toLowerCase().includes(query),
      );
    }
    if (cat) {
      items = items.filter((n) => n.category === cat);
    }
    return items;
  });

  protected groupedNodeTypes = computed(() => {
    const groups: Record<string, NodeTypeRecord[]> = {};
    for (const nt of this.filteredNodeTypes()) {
      const cat = nt.category || 'other';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(nt);
    }
    return Object.keys(groups)
      .sort()
      .map((key) => ({ category: key, types: groups[key] }));
  });

  protected enabledCount = computed(() => this.nodeTypes().filter((n) => n.enabled).length);
  protected totalCount = computed(() => this.nodeTypes().length);

  async ngOnInit() {
    this.navService.setPageConfig({
      title: 'Node Definitions',
      subtitle: 'Manage available node types in the processing palette',
    });
    await this.loadNodeTypes();
  }

  private async loadNodeTypes() {
    this.isLoading.set(true);
    try {
      const types = await this.adminApi.getNodeTypes();
      this.nodeTypes.set(types);
    } catch (err) {
      console.error('Failed to load node types', err);
      this.toast.danger('Failed to load node types.');
    } finally {
      this.isLoading.set(false);
    }
  }

  protected async onToggle(nodeType: NodeTypeRecord) {
    const newEnabled = !nodeType.enabled;
    this.togglingType.set(nodeType.type);
    try {
      const result = await this.adminApi.setNodeTypeEnabled(nodeType.type, newEnabled);
      this.nodeTypes.update((types) =>
        types.map((t) => (t.type === nodeType.type ? { ...t, enabled: newEnabled } : t)),
      );

      if (newEnabled) {
        this.toast.success(`${nodeType.display_name} enabled.`);
      } else {
        const msg =
          result.disabled_instances.length > 0
            ? `${nodeType.display_name} disabled. ${result.disabled_instances.length} DAG instance(s) also disabled.`
            : `${nodeType.display_name} disabled.`;
        this.toast.warning(msg);
      }
    } catch (err) {
      console.error('Failed to toggle node type', err);
      this.toast.danger(`Failed to toggle ${nodeType.display_name}.`);
    } finally {
      this.togglingType.set(null);
    }
  }

  protected onSearch(event: Event) {
    this.searchQuery.set((event.target as HTMLInputElement).value);
  }

  protected onFilterCategory(category: string | null) {
    this.filterCategory.set(this.filterCategory() === category ? null : category);
  }

  protected getCategoryIcon(category: string): string {
    const map: Record<string, string> = {
      sensor: 'sensors',
      fusion: 'merge',
      operation: 'build',
      calibration: 'tune',
      application: 'apps',
      flow_control: 'account_tree',
    };
    return map[category] ?? 'extension';
  }
}
