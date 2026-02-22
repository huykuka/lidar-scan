# Quick Start: Adding a Custom Node Plugin

## 1. Create Your Plugin (2 minutes)

Create `web/src/app/plugins/my-plugin.ts`:

```typescript
import { NodePlugin } from '../core/models/node-plugin.model';

export const myAwesomePlugin: NodePlugin = {
  type: 'awesome-processor',
  displayName: 'Awesome Processor',
  description: 'Process point clouds awesomely',
  icon: 'auto_awesome',
  style: {
    color: '#ec4899',       // Pink
    backgroundColor: '#fdf2f8',
  },
  createInstance: () => ({
    type: 'awesome-processor',
    name: 'New Awesome Processor',
    enabled: false,
    processingMode: 'fast',
  }),
  renderBody: (data) => ({
    fields: [
      { label: 'Mode', value: data.processingMode || 'fast' },
    ],
  }),
};
```

## 2. Register It (30 seconds)

In your `app.component.ts`:

```typescript
import { Component, inject, OnInit } from '@angular/core';
import { NodePluginRegistry } from './core/services/node-plugin-registry.service';
import { myAwesomePlugin } from './plugins/my-plugin';

export class AppComponent implements OnInit {
  private registry = inject(NodePluginRegistry);

  ngOnInit() {
    this.registry.register(myAwesomePlugin);
  }
}
```

## 3. See It in Action (instant)

1. Refresh your browser
2. Open Settings page
3. Your plugin appears in the left palette!
4. Drag it onto the canvas

## That's It! 🎉

Your plugin is now available in the flow canvas. Users can:
- Drag it from the palette
- Position it on the canvas
- See its properties
- Enable/disable it

## Next Steps

### Add Backend Processing

Create `app/services/nodes/awesome_processor.py`:

```python
class AwesomeProcessor:
    def __init__(self, config):
        self.config = config
    
    def process(self, point_cloud):
        # Your awesome processing here
        return processed_cloud
```

### Add an Editor Component

Create a full editor dialog like `LidarEditorComponent`:

```typescript
@Component({
  selector: 'app-awesome-editor',
  template: `
    <syn-dialog>
      <syn-input [(ngModel)]="config.name" label="Name"></syn-input>
      <syn-select [(ngModel)]="config.processingMode" label="Mode">
        <syn-option value="fast">Fast</syn-option>
        <syn-option value="accurate">Accurate</syn-option>
      </syn-select>
    </syn-dialog>
  `,
})
export class AwesomeEditorComponent { }
```

Then add to your plugin:
```typescript
editorComponent: AwesomeEditorComponent
```

## Plugin Examples

See `web/src/app/plugins/example-plugins.ts` for complete examples:
- **Transform Node** - Spatial transformations
- **Filter Node** - Outlier removal  
- **Recording Node** - Save to disk

## Full Documentation

- **Complete Guide**: `PLUGIN_GUIDE.md`
- **Connections & System**: `FLOW_CANVAS_CONNECTIONS.md`
- **Plugin API**: `web/src/app/core/models/node-plugin.model.ts`
