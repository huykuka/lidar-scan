import {
  Component,
  ComponentRef,
  effect,
  inject,
  OnDestroy,
  output,
  signal,
  untracked,
  viewChild,
  ViewContainerRef,
} from '@angular/core';

import {NodeStoreService} from '@core/services/stores/node-store.service';
import {NodePluginRegistry} from '@core/services/node-plugin-registry.service';
import {NodeEditorComponent} from '@core/models/node-plugin.model';

@Component({
  selector: 'app-dynamic-node-editor',
  imports: [],
  templateUrl: './dynamic-node-editor.component.html',
  styleUrl: './dynamic-node-editor.component.css',
})
export class DynamicNodeEditorComponent implements OnDestroy {
  save = output<void>();
  cancel = output<void>();
  private nodeStore = inject(NodeStoreService);
  private pluginRegistry = inject(NodePluginRegistry);
  editorHost = viewChild('editorHost', {read: ViewContainerRef});
  private pluginEditorRef = signal<ComponentRef<NodeEditorComponent> | null>(null);

  constructor() {
    effect(() => {
      const nodeData = this.nodeStore.selectedNode();
      const container = this.editorHost();

      if (!container || !nodeData || !nodeData.type) {
        this.destroyPluginEditor();
        return;
      }

      const plugin = this.pluginRegistry.get(nodeData.type);
      if (!plugin?.editorComponent) {
        this.destroyPluginEditor();
        return;
      }

      // Capture editorComponent before untracked() to preserve type narrowing
      const editorComponent = plugin.editorComponent;

      // Wrap component creation in untracked() to prevent child signal reads from re-triggering this effect
      untracked(() => {
        this.destroyPluginEditor();
        const componentRef = container.createComponent(editorComponent);
        componentRef.instance.saved.subscribe(() => this.save.emit());
        componentRef.instance.cancelled.subscribe(() => this.cancel.emit());
        this.pluginEditorRef.set(componentRef);
      });
    });
  }

  ngOnDestroy() {
    this.destroyPluginEditor();
  }

  private destroyPluginEditor(): void {
    const ref = this.pluginEditorRef();
    if (ref) {
      ref.destroy();
      this.pluginEditorRef.set(null);
    }
  }
}
