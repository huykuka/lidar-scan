# Example Plugin Usage

This file demonstrates how to register and use custom node plugins.

## Registering Example Plugins

To enable the example plugins (Transform, Filter, Recording), add them to your application:

### In app.config.ts or main component:

```typescript
import { APP_INITIALIZER } from '@angular/core';
import { NodePluginRegistry } from './core/services/node-plugin-registry.service';
import { 
  transformNodePlugin, 
  filterNodePlugin, 
  recordingNodePlugin 
} from './plugins/example-plugins';

export const appConfig: ApplicationConfig = {
  providers: [
    // ... other providers
    {
      provide: APP_INITIALIZER,
      useFactory: (registry: NodePluginRegistry) => () => {
        // Register example plugins
        registry.register(transformNodePlugin);
        registry.register(filterNodePlugin);
        registry.register(recordingNodePlugin);
        console.log('Custom plugins registered!');
      },
      deps: [NodePluginRegistry],
      multi: true,
    },
  ],
};
```

### In a standalone component:

```typescript
import { Component, inject, OnInit } from '@angular/core';
import { NodePluginRegistry } from './core/services/node-plugin-registry.service';
import { transformNodePlugin } from './plugins/example-plugins';

@Component({
  selector: 'app-root',
  template: '...',
})
export class AppComponent implements OnInit {
  private pluginRegistry = inject(NodePluginRegistry);

  ngOnInit() {
    // Register custom plugins
    this.pluginRegistry.register(transformNodePlugin);
  }
}
```

## Creating a New Plugin

1. Create a new file in `web/src/app/plugins/`:

```typescript
// my-plugin.ts
import { NodePlugin } from '../core/models/node-plugin.model';

export const myPlugin: NodePlugin = {
  type: 'my-custom-type',
  displayName: 'My Custom Node',
  description: 'What this node does',
  icon: 'settings', // Material icon name
  style: {
    color: '#10b981',
    backgroundColor: '#ecfdf5',
  },
  createInstance: () => ({
    type: 'my-custom-type',
    name: 'New Node',
    enabled: false,
    // Your custom properties
  }),
  renderBody: (data) => ({
    fields: [
      { label: 'Property', value: data.myProperty },
    ],
  }),
};
```

2. Register it in your app initialization
3. Refresh the flow canvas - your node will appear in the palette!

## Backend Integration

To make your node functional, add backend support:

```python
# app/services/nodes/my_node.py
class MyCustomNode:
    def __init__(self, config):
        self.config = config
        self.enabled = config.get('enabled', False)
    
    def start(self):
        # Start processing
        pass
    
    def process(self, data):
        # Process data
        return modified_data
    
    def stop(self):
        # Cleanup
        pass
```

See PLUGIN_GUIDE.md for complete documentation.
