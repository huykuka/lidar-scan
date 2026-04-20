import {inject, Injectable} from '@angular/core';
import {NodeData, NodePlugin} from '@core/models';
import {NodesApiService} from '@core/services/api';
import {NodeStoreService} from '@core/services/stores';
import {NodeDefinition} from '../models/node.model';
import {SensorNodeCardComponent} from '@plugins/sensor/node/sensor-node-card.component';
import {SensorNodeEditorComponent} from '@plugins/sensor/form/sensor-node-editor.component';
import {FusionNodeCardComponent} from '@plugins/fusion/node/fusion-node-card.component';
import {FusionNodeEditorComponent} from '@plugins/fusion/form/fusion-node-editor.component';
import {OperationNodeCardComponent} from '@plugins/operation/node/operation-node-card.component';
import {OperationNodeEditorComponent} from '@plugins/operation/form/operation-node-editor.component';
import {CalibrationNodeCardComponent} from '@plugins/calibration/node/calibration-node-card.component';
import {CalibrationNodeEditorComponent} from '@plugins/calibration/form/calibration-node-editor.component';
import {IfConditionCardComponent} from '@plugins/flow-control/if-block/node/if-condition-card.component';
import {IfConditionEditorComponent} from '@plugins/flow-control/if-block/form/if-condition-editor.component';
import {OutputNodeCardComponent} from '@plugins/flow-control/output/node/output-node-card/output-node-card.component';
import {OutputNodeEditorComponent} from '@plugins/flow-control/output/form/output-node-editor/output-node-editor.component';
import {PlaybackNodeCardComponent} from '@plugins/playback/node/playback-node-card/playback-node-card.component';
import {PlaybackNodeEditorComponent} from '@plugins/playback/form/playback-node-editor/playback-node-editor.component';

/** Visual metadata per category — used to style the palette and canvas nodes. */
const CATEGORY_STYLE: Record<string, { color: string; icon: string }> = {
  sensor: {color: '#10b981', icon: 'sensors'},
  fusion: {color: '#6366f1', icon: 'hub'},
  calibration: {color: '#f59e0b', icon: 'tune'},
  operation: {color: '#64748b', icon: 'settings_input_component'},
  flow_control: {color: '#9c27b0', icon: 'call_split'},
  output: {color: '#0ea5e9', icon: 'dashboard'},
};

function definitionToPlugin(def: NodeDefinition): NodePlugin {
  const style = CATEGORY_STYLE[def.category] ?? {color: '#64748b', icon: 'extension'};

  return {
    type: def.type,
    category: def.category,
    displayName: def.display_name,
    description: def.description ?? '',
    icon: def.icon ?? style.icon,
    style: {color: style.color},
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
      config: def.category === 'operation' ? {op_type: def.type} : {},
    }),
    renderBody: (data: NodeData) => ({fields: []}),
  };
}

/**
 * NodePluginRegistry
 *
 * The palette and canvas use this service to know what node types are
 * available. Types are loaded from the backend `/nodes/definitions` endpoint
 * and stored in the NodeStore. No local hardcoding of schemas.
 */
@Injectable({providedIn: 'root'})
export class NodePluginRegistry {
  private nodesApi = inject(NodesApiService);
  private nodeStore = inject(NodeStoreService);

  private plugins = new Map<string, NodePlugin>();

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
      this.registerPluginComponents();
    } catch (err) {
      console.error('NodePluginRegistry: Failed to load definitions from backend', err);
    }
  }

  private registerPluginComponents(): void {
    this.plugins.forEach((plugin, type) => {
      // output_node gets its own dedicated card + editor (must be checked BEFORE flow_control)
      if (type === 'output_node') {
        this.plugins.set(type, {
          ...plugin,
          cardComponent: OutputNodeCardComponent,
          editorComponent: OutputNodeEditorComponent,
        });
        return;
      }
      if (plugin.category === 'sensor') {
        this.plugins.set(type, {
          ...plugin,
          cardComponent: type === 'playback' ? PlaybackNodeCardComponent : SensorNodeCardComponent,
          editorComponent: type === 'playback' ? PlaybackNodeEditorComponent : SensorNodeEditorComponent,
        });
      }
      if (plugin.category === 'fusion') {
        this.plugins.set(type, {
          ...plugin,
          cardComponent: FusionNodeCardComponent,
          editorComponent: FusionNodeEditorComponent,
        });
      }
      if (plugin.category === 'operation') {
        this.plugins.set(type, {
          ...plugin,
          cardComponent: OperationNodeCardComponent,
          editorComponent: OperationNodeEditorComponent,
        });
      }
      if (plugin.category === 'calibration') {
        this.plugins.set(type, {
          ...plugin,
          cardComponent: CalibrationNodeCardComponent,
          editorComponent: CalibrationNodeEditorComponent,
        });
      }
      if (plugin.category === 'flow_control') {
        this.plugins.set(type, {
          ...plugin,
          cardComponent: IfConditionCardComponent,
          editorComponent: IfConditionEditorComponent,
        });
      }
    });
  }


  get(type: string): NodePlugin | undefined {
    return this.plugins.get(type);
  }

  getAll(): NodePlugin[] {
    return Array.from(this.plugins.values());
  }
}
