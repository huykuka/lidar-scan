import { Injectable } from '@angular/core';
import { NodePlugin, NodeData } from '../models/node-plugin.model';
import { NodesApiService } from './api/nodes-api.service';
import { NodeStoreService } from './stores/node-store.service';
import { NodeDefinition } from '../models/node.model';

/** Visual metadata per category — used to style the palette and canvas nodes. */
const CATEGORY_STYLE: Record<string, { color: string; icon: string }> = {
  sensor: { color: '#10b981', icon: 'sensors' },
  fusion: { color: '#6366f1', icon: 'hub' },
  operation: { color: '#f59e0b', icon: 'settings_input_component' },
};

function definitionToPlugin(def: NodeDefinition): NodePlugin {
  const style = CATEGORY_STYLE[def.category] ?? { color: '#64748b', icon: 'extension' };

  return {
    type: def.type,
    category: def.category,
    displayName: def.display_name,
    description: def.description ?? '',
    icon: def.icon ?? style.icon,
    style: { color: style.color },
    ports: {
      inputs:
        def.inputs?.map((p: any) => ({
          id: p.id,
          label: p.label,
          dataType: p.data_type ?? 'pointcloud',
          multiple: p.multiple ?? false,
        })) ?? [],
      outputs:
        def.outputs?.map((p: any) => ({
          id: p.id,
          label: p.label,
          dataType: p.data_type ?? 'pointcloud',
          multiple: p.multiple ?? false,
        })) ?? [],
    },
    /** Default instance — type and category from backend, empty config. */
    createInstance: () => ({
      type: def.type,
      category: def.category,
      name: def.display_name,
      enabled: true,
      config: def.category === 'operation' ? { op_type: def.type } : {},
    }),
    renderBody: (data: NodeData) => ({ fields: [] }),
  };
}

/**
 * NodePluginRegistry
 *
 * The palette and canvas use this service to know what node types are
 * available. Types are loaded from the backend `/nodes/definitions` endpoint
 * and stored in the NodeStore. No local hardcoding of schemas.
 */
@Injectable({ providedIn: 'root' })
export class NodePluginRegistry {
  private plugins = new Map<string, NodePlugin>();

  constructor(
    private nodesApi: NodesApiService,
    private nodeStore: NodeStoreService,
  ) {}

  /**
   * Load all node types from the backend and populate the registry.
   * Called once on app/component init.
   */
  async loadFromBackend(): Promise<void> {
    try {
      const definitions = await this.nodesApi.getNodeDefinitions();
      this.nodeStore.set('nodeDefinitions', definitions);
      this.plugins.clear();
      definitions.forEach((def) => this.plugins.set(def.type, definitionToPlugin(def)));
      console.log(
        `NodePluginRegistry: Loaded ${definitions.length} definitions:`,
        definitions.map((d) => d.type),
      );
    } catch (err) {
      console.error('NodePluginRegistry: Failed to load definitions from backend', err);
    }
  }

  register(plugin: NodePlugin): void {
    this.plugins.set(plugin.type, plugin);
  }

  get(type: string): NodePlugin | undefined {
    return this.plugins.get(type);
  }

  getAll(): NodePlugin[] {
    return Array.from(this.plugins.values());
  }

  has(type: string): boolean {
    return this.plugins.has(type);
  }

  getByCategory(category: string): NodePlugin[] {
    return this.getAll().filter((p) => {
      const def = this.nodeStore.nodeDefinitions().find((d) => d.type === p.type);
      return def?.category === category;
    });
  }
}
