# Node Plugin Development Guide

This guide explains how to create custom node plugins for the LiDAR flow canvas.

## Overview

The plugin system allows you to extend the flow canvas with custom node types. Plugins define:
- Visual appearance (icon, colors)
- Data structure
- Connection ports
- Editor components
- Validation logic

## Plugin Structure

A plugin implements the `NodePlugin` interface:

```typescript
import { NodePlugin } from '../core/models/node-plugin.model';

export const myCustomPlugin: NodePlugin = {
  type: 'my-custom-node',
  displayName: 'My Custom Node',
  description: 'Description shown in palette',
  icon: 'icon-name', // Synergy icon name
  style: {
    color: '#f59e0b',           // Border/accent color
    backgroundColor: '#fffbeb', // Background color
  },
  ports: {
    inputs: [
      {
        id: 'input1',
        label: 'Input Data',
        dataType: 'pointcloud',
        multiple: false, // Allow multiple connections
      }
    ],
    outputs: [
      {
        id: 'output1',
        label: 'Processed Data',
        dataType: 'pointcloud',
        multiple: true,
      }
    ],
  },
  createInstance: () => ({
    type: 'my-custom-node',
    name: 'New Custom Node',
    enabled: false,
    customProperty: 'default value',
  }),
  renderBody: (data) => ({
    fields: [
      { label: 'Status', value: data.customProperty },
      { label: 'Count', value: 42, type: 'number' },
    ],
  }),
  validate: (data) => {
    const errors = [];
    if (!data.name) {
      errors.push('Name is required');
    }
    return {
      valid: errors.length === 0,
      errors,
    };
  },
  editorComponent: MyCustomEditorComponent, // Optional
};
```

## Registering a Plugin

### Option 1: Register at Application Startup

In your `app.config.ts` or main component:

```typescript
import { inject } from '@angular/core';
import { NodePluginRegistry } from './core/services/node-plugin-registry.service';
import { myCustomPlugin } from './plugins/my-custom-plugin';

export function initializePlugins() {
  return () => {
    const registry = inject(NodePluginRegistry);
    registry.register(myCustomPlugin);
  };
}

// In app.config.ts providers:
{
  provide: APP_INITIALIZER,
  useFactory: initializePlugins,
  multi: true,
}
```

### Option 2: Register Dynamically

```typescript
import { Component, inject, OnInit } from '@angular/core';
import { NodePluginRegistry } from './core/services/node-plugin-registry.service';

@Component({...})
export class MyComponent implements OnInit {
  private registry = inject(NodePluginRegistry);

  ngOnInit() {
    this.registry.register({
      type: 'dynamic-node',
      displayName: 'Dynamic Node',
      // ... rest of plugin definition
    });
  }
}
```

## Example: Filter Node

Here's a complete example of a point cloud filter node:

```typescript
// plugins/filter-node.plugin.ts
import { NodePlugin } from '../core/models/node-plugin.model';

export const filterNodePlugin: NodePlugin = {
  type: 'filter',
  displayName: 'Filter Node',
  description: 'Filter point cloud data',
  icon: 'filter_alt',
  style: {
    color: '#8b5cf6',
    backgroundColor: '#f5f3ff',
  },
  ports: {
    inputs: [
      {
        id: 'input',
        label: 'Point Cloud Input',
        dataType: 'pointcloud',
        multiple: false,
      }
    ],
    outputs: [
      {
        id: 'output',
        label: 'Filtered Output',
        dataType: 'pointcloud',
        multiple: true,
      }
    ],
  },
  createInstance: () => ({
    type: 'filter',
    name: 'New Filter',
    enabled: false,
    filterType: 'statistical',
    threshold: 2.0,
  }),
  renderBody: (data) => {
    const filterData = data as FilterNodeData;
    return {
      fields: [
        { label: 'Type', value: filterData.filterType },
        { label: 'Threshold', value: filterData.threshold, type: 'number' },
      ],
    };
  },
  validate: (data) => {
    const errors = [];
    const filterData = data as FilterNodeData;
    
    if (!filterData.filterType) {
      errors.push('Filter type is required');
    }
    
    if (filterData.threshold <= 0) {
      errors.push('Threshold must be positive');
    }
    
    return {
      valid: errors.length === 0,
      errors,
    };
  },
  editorComponent: FilterEditorComponent,
};

interface FilterNodeData {
  type: string;
  name: string;
  enabled: boolean;
  filterType: 'statistical' | 'radius' | 'voxel';
  threshold: number;
}
```

## Backend Integration

To make your custom node functional, you need to:

1. **Update Backend Models**: Add your node type to backend models
2. **Implement Worker**: Create a worker process for your node
3. **Add API Endpoints**: Expose CRUD operations
4. **Register in Service**: Add to the lidar/fusion service orchestrator

Example backend structure:

```python
# app/services/nodes/filter_node.py
class FilterNode:
    def __init__(self, config):
        self.config = config
        self.process = None
    
    def start(self):
        # Start worker process
        pass
    
    def stop(self):
        # Stop worker process
        pass
```

## Available Icon Names

Use any Material Icons from Synergy Design System:
- `sensors`, `hub`, `filter_alt`
- `transform`, `layers`, `tune`
- `analytics`, `memory`, `settings_input_component`

Full list: https://fonts.google.com/icons

## Port Types

Common port data types:
- `pointcloud` - Point cloud data
- `image` - Image data
- `transform` - Transformation matrix
- `config` - Configuration data
- `any` - Accept any type

## Tips

1. **Unique Types**: Use unique type identifiers (e.g., `company-feature-node`)
2. **Validation**: Always implement validate() to prevent invalid configurations
3. **Colors**: Use consistent color schemes for related nodes
4. **Descriptions**: Write clear, concise descriptions for the palette
5. **Icons**: Choose icons that clearly represent the node's function

## Testing Your Plugin

```typescript
import { TestBed } from '@angular/core/testing';
import { NodePluginRegistry } from './core/services/node-plugin-registry.service';
import { myCustomPlugin } from './plugins/my-custom-plugin';

describe('My Custom Plugin', () => {
  let registry: NodePluginRegistry;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    registry = TestBed.inject(NodePluginRegistry);
    registry.register(myCustomPlugin);
  });

  it('should register successfully', () => {
    expect(registry.has('my-custom-node')).toBe(true);
  });

  it('should create valid instance', () => {
    const plugin = registry.get('my-custom-node')!;
    const instance = plugin.createInstance();
    const result = plugin.validate?.(instance);
    expect(result?.valid).toBe(true);
  });
});
```

## Plugin Distribution

To distribute your plugin:

1. Create an npm package with your plugin
2. Export the plugin definition
3. Document installation and registration
4. Provide backend integration code if needed

Example package structure:
```
my-lidar-plugin/
├── src/
│   ├── plugin.ts           # Plugin definition
│   ├── editor.component.ts # Editor component
│   └── index.ts            # Public API
├── backend/
│   └── worker.py           # Backend worker
├── README.md
└── package.json
```

## Examples Repository

Check out the examples repository for complete plugin implementations:
- Filter Node
- Transform Node
- Analytics Node
- Recording Node

[Link to examples repo when available]
