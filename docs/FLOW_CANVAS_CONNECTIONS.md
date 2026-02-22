# Flow Canvas - Node Connections & Plugin System

## Overview

The flow canvas now includes:
1. **Visual Connections** - Lines between sensor and fusion nodes
2. **Plugin System** - Extensible architecture for custom node types
3. **Port Indicators** - Visual connection points on nodes

## Connection Visualization

### How Connections Work
- **Automatic Detection**: Connections are automatically calculated based on fusion node `sensor_ids`
- **SVG Rendering**: Smooth bezier curves connect sensor outputs to fusion inputs
- **Real-time Updates**: Connections update when nodes are moved or configurations change

### Visual Elements
- **Sensors**: Green output port on the right side
- **Fusions**: Blue input port on the left side
- **Connection Lines**: Blue arrows flowing from sensors to fusions

### Connection Path Calculation
```typescript
// Smooth cubic bezier curve
const fromX = sensorNode.position.x + nodeWidth;    // Right edge of sensor
const fromY = sensorNode.position.y + nodeHeight/2; // Middle of sensor
const toX = fusionNode.position.x;                  // Left edge of fusion
const toY = fusionNode.position.y + nodeHeight/2;   // Middle of fusion

// Control points create smooth curve
const controlPointOffset = Math.abs(toX - fromX) * 0.5;
path = `M ${fromX} ${fromY} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${toX} ${toY}`;
```

## Plugin System Architecture

### Core Components

1. **NodePlugin Interface** (`core/models/node-plugin.model.ts`)
   - Defines plugin structure
   - Includes ports, styling, validation
   - Factory methods for instances

2. **NodePluginRegistry Service** (`core/services/node-plugin-registry.service.ts`)
   - Singleton service for plugin management
   - Built-in sensor and fusion plugins
   - Runtime registration/unregistration

3. **Example Plugins** (`plugins/example-plugins.ts`)
   - Transform Node - Apply transformations
   - Filter Node - Statistical outlier removal
   - Recording Node - Save to disk

### Built-in Plugins

#### Sensor Node
```typescript
{
  type: 'sensor',
  displayName: 'Sensor Node',
  icon: 'sensors',
  color: '#10b981', // green
  ports: {
    outputs: [
      { id: 'raw_points', label: 'Raw Points' },
      { id: 'processed_points', label: 'Processed Points' }
    ]
  }
}
```

#### Fusion Node
```typescript
{
  type: 'fusion',
  displayName: 'Fusion Node',
  icon: 'hub',
  color: '#6366f1', // indigo
  ports: {
    inputs: [{ id: 'sensor_inputs', multiple: true }],
    outputs: [{ id: 'fused_output' }]
  }
}
```

## Adding Custom Plugins

### Step 1: Define Your Plugin

Create a new file `plugins/my-plugin.ts`:

```typescript
import { NodePlugin } from '../core/models/node-plugin.model';

export const myPlugin: NodePlugin = {
  type: 'my-custom-type',
  displayName: 'My Custom Node',
  description: 'What this node does',
  icon: 'settings', // Material icon
  style: {
    color: '#f59e0b',       // Amber
    backgroundColor: '#fffbeb',
  },
  ports: {
    inputs: [{
      id: 'input',
      label: 'Input Data',
      dataType: 'pointcloud',
      multiple: false,
    }],
    outputs: [{
      id: 'output',
      label: 'Output Data',
      dataType: 'pointcloud',
      multiple: true,
    }],
  },
  createInstance: () => ({
    type: 'my-custom-type',
    name: 'New Node',
    enabled: false,
    customProperty: 'value',
  }),
  renderBody: (data) => ({
    fields: [
      { label: 'Property', value: data.customProperty },
      { label: 'Count', value: 42, type: 'number' },
    ],
  }),
  validate: (data) => {
    const errors = [];
    if (!data.name) {
      errors.push('Name is required');
    }
    return { valid: errors.length === 0, errors };
  },
};
```

### Step 2: Register Your Plugin

**Option A: At Application Startup**

In `app.config.ts`:
```typescript
import { APP_INITIALIZER } from '@angular/core';
import { NodePluginRegistry } from './core/services/node-plugin-registry.service';
import { myPlugin } from './plugins/my-plugin';

export const appConfig: ApplicationConfig = {
  providers: [
    {
      provide: APP_INITIALIZER,
      useFactory: (registry: NodePluginRegistry) => () => {
        registry.register(myPlugin);
      },
      deps: [NodePluginRegistry],
      multi: true,
    },
  ],
};
```

**Option B: In a Component**

```typescript
import { Component, inject, OnInit } from '@angular/core';
import { NodePluginRegistry } from './core/services/node-plugin-registry.service';
import { myPlugin } from './plugins/my-plugin';

@Component({...})
export class AppComponent implements OnInit {
  private pluginRegistry = inject(NodePluginRegistry);

  ngOnInit() {
    this.pluginRegistry.register(myPlugin);
  }
}
```

### Step 3: Implement Backend Support

Create backend handler in `app/services/nodes/my_node.py`:

```python
class MyCustomNode:
    def __init__(self, config):
        self.config = config
        self.enabled = config.get('enabled', False)
        self.process = None
    
    def start(self):
        """Start the node processing"""
        if not self.enabled:
            return
        
        # Start worker process
        self.process = multiprocessing.Process(
            target=self._worker,
            args=(self.config,)
        )
        self.process.start()
    
    def _worker(self, config):
        """Worker process logic"""
        while True:
            # Process data
            data = receive_data()
            result = self.process_data(data)
            send_result(result)
    
    def stop(self):
        """Stop the node"""
        if self.process:
            self.process.terminate()
            self.process = None
    
    def process_data(self, data):
        """Your custom processing logic"""
        return modified_data
```

### Step 4: Update Backend API

Add to `app/api/v1/nodes.py`:

```python
@router.post("/my-custom-nodes/")
async def create_my_custom_node(config: MyCustomNodeConfig):
    # Store config in database
    # Return created node
    pass

@router.get("/my-custom-nodes/")
async def list_my_custom_nodes():
    # Fetch from database
    pass
```

## Plugin Features

### Port System
- **Inputs**: Left side of node (blue)
- **Outputs**: Right side of node (green)
- **Multiple Connections**: Support for fan-in/fan-out
- **Data Type Validation**: Type checking for connections

### Visual Customization
- **Colors**: Border and background colors
- **Icons**: Material Design icons
- **Badges**: Status indicators
- **Fields**: Custom property display

### Validation
- **Required Fields**: Name, type, etc.
- **Range Checks**: Min/max values
- **Custom Logic**: Plugin-specific validation
- **Error Display**: Visual feedback in UI

## Example Plugins Included

### 1. Transform Node
- **Purpose**: Apply spatial transformations
- **Properties**: Translation, rotation, scale
- **Ports**: 1 input, 1 output
- **Color**: Amber (#f59e0b)

### 2. Filter Node
- **Purpose**: Remove outliers
- **Properties**: Filter type, neighbors, threshold
- **Ports**: 1 input, 1 output
- **Color**: Purple (#8b5cf6)

### 3. Recording Node
- **Purpose**: Save point clouds to disk
- **Properties**: Output path, format, max files
- **Ports**: 1 input, 0 outputs
- **Color**: Red (#ef4444)

## Best Practices

1. **Unique Type IDs**: Use namespaced types (e.g., `company-feature-node`)
2. **Clear Naming**: Use descriptive display names and descriptions
3. **Validation**: Always implement validate() method
4. **Icons**: Choose intuitive Material icons
5. **Colors**: Use consistent color schemes
6. **Testing**: Write tests for plugin logic
7. **Documentation**: Document plugin behavior and properties

## Plugin Distribution

To share your plugin:

1. Create npm package with plugin definition
2. Include TypeScript types
3. Provide backend integration code
4. Add installation instructions
5. Include example usage

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

## Future Enhancements

- **Dynamic Connections**: Drag-to-connect between nodes
- **Connection Validation**: Type checking for port connections
- **Plugin Marketplace**: Browse and install community plugins
- **Hot Reload**: Update plugins without restart
- **Plugin Categories**: Organize plugins by function
- **Connection Properties**: Configure connection-specific settings

## Resources

- **Plugin Guide**: `PLUGIN_GUIDE.md`
- **Example Plugins**: `web/src/app/plugins/example-plugins.ts`
- **Plugin API**: `web/src/app/core/models/node-plugin.model.ts`
- **Registry Service**: `web/src/app/core/services/node-plugin-registry.service.ts`

## Support

For questions or issues:
1. Check the Plugin Guide documentation
2. Review example plugins
3. Open an issue on GitHub
4. Join the community discussions
