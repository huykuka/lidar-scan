import { Injectable, Type, inject } from '@angular/core';
import { NodePlugin, NodeData } from '../models/node-plugin.model';
import { LidarConfig } from '../models/lidar.model';
import { FusionConfig } from '../models/fusion.model';
import { LidarEditorComponent } from '../../features/settings/components/lidar-editor/lidar-editor';
import { FusionEditorComponent } from '../../features/settings/components/fusion-editor/fusion-editor';

/**
 * Node Plugin Registry Service
 * 
 * Manages registration and retrieval of node plugins for the flow canvas.
 * Plugins can be registered at runtime to extend the system with new node types.
 */
@Injectable({
  providedIn: 'root',
})
export class NodePluginRegistry {
  private plugins = new Map<string, NodePlugin>();

  constructor() {
    // Register built-in node types
    this.registerBuiltInPlugins();
  }

  /**
   * Register a new node plugin
   */
  register(plugin: NodePlugin): void {
    if (this.plugins.has(plugin.type)) {
      console.warn(`Plugin type "${plugin.type}" is already registered. Overwriting.`);
    }
    this.plugins.set(plugin.type, plugin);
    console.log(`Node plugin registered: ${plugin.type} (${plugin.displayName})`);
  }

  /**
   * Unregister a node plugin
   */
  unregister(type: string): boolean {
    return this.plugins.delete(type);
  }

  /**
   * Get a specific plugin by type
   */
  get(type: string): NodePlugin | undefined {
    return this.plugins.get(type);
  }

  /**
   * Get all registered plugins
   */
  getAll(): NodePlugin[] {
    return Array.from(this.plugins.values());
  }

  /**
   * Get plugins filtered by category/tag
   */
  getByCategory(category: string): NodePlugin[] {
    // Future: Add category support to NodePlugin interface
    return this.getAll();
  }

  /**
   * Check if a plugin type is registered
   */
  has(type: string): boolean {
    return this.plugins.has(type);
  }

  /**
   * Register built-in node types (Sensor and Fusion)
   */
  private registerBuiltInPlugins(): void {
    // Sensor Node Plugin
    this.register({
      type: 'sensor',
      displayName: 'Sensor Node',
      description: 'Lidar hardware or simulated sensor',
      icon: 'sensors',
      style: {
        color: '#10b981', // green
        backgroundColor: '#ecfdf5',
      },
      ports: {
        outputs: [
          {
            id: 'raw_points',
            label: 'Raw Points',
            dataType: 'pointcloud',
            multiple: true,
          },
          {
            id: 'processed_points',
            label: 'Processed Points',
            dataType: 'pointcloud',
            multiple: true,
          },
        ],
      },
      createInstance: () => ({
        type: 'sensor',
        name: 'New Sensor',
        enabled: false,
      }),
      renderBody: (data: NodeData) => ({
        fields: [
          { label: 'Type', value: (data as any).driver || 'N/A' },
          { label: 'Topic', value: (data as any).topic_prefix || 'N/A', type: 'text' },
        ],
      }),
      editorComponent: LidarEditorComponent,
    });

    // Fusion Node Plugin
    this.register({
      type: 'fusion',
      displayName: 'Fusion Node',
      description: 'Merge multiple sensors',
      icon: 'hub',
      style: {
        color: '#6366f1', // indigo
        backgroundColor: '#eef2ff',
      },
      ports: {
        inputs: [
          {
            id: 'sensor_inputs',
            label: 'Sensor Inputs',
            dataType: 'pointcloud',
            multiple: true,
          },
        ],
        outputs: [
          {
            id: 'fused_output',
            label: 'Fused Output',
            dataType: 'pointcloud',
            multiple: true,
          },
        ],
      },
      createInstance: () => ({
        type: 'fusion',
        name: 'New Fusion',
        enabled: false,
        sensor_ids: [],
        pipeline: 'default',
      }),
      renderBody: (data: NodeData) => ({
        fields: [
          { label: 'Sensors', value: (data as any).sensor_ids?.length || 0, type: 'number' },
          { label: 'Pipeline', value: (data as any).pipeline || 'default' },
        ],
      }),
      editorComponent: FusionEditorComponent,
    });
  }
}
