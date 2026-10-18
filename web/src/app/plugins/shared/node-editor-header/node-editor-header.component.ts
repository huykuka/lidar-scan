import {ChangeDetectionStrategy, Component, inject, input, output} from '@angular/core';
import {NgClass} from '@angular/common';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {AuthService} from '@core/services/auth.service';
import {ToastService} from '@core/services/toast.service';

@Component({
  selector: 'app-node-editor-header',

  imports: [SynergyComponentsModule, NgClass],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './node-editor-header.component.html',
})
export class NodeEditorHeaderComponent {
  icon = input<string>('settings');
  iconColor = input<string>('text-syn-color-primary-600');
  title = input<string>('');
  description = input<string | undefined>(undefined);
  saveDisabled = input<boolean>(false);

  save = output<void>();
  cancel = output<void>();

  protected nodeStore = inject(NodeStoreService);
  protected auth = inject(AuthService);
  private toast = inject(ToastService);

  protected async copyNodeId(id: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(id);
      this.toast.success('Node ID copied');
    } catch {
      this.toast.danger('Could not copy node ID');
    }
  }

  protected exportConfig(): void {
    const { type, name, config, pose } = this.nodeStore.selectedNode();
    const blob = new Blob([JSON.stringify({ type, name, config, pose }, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(name || type || 'node').replace(/[^\w.-]+/g, '_')}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  protected async onImportFileSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = ''; // allow re-importing the same file
    if (!file) return;

    let parsed: any;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      this.toast.danger('Invalid JSON file');
      return;
    }
    const current = this.nodeStore.selectedNode();
    if (!parsed || typeof parsed.config !== 'object' || parsed.config === null) {
      this.toast.danger('File does not contain a node config');
      return;
    }
    if (parsed.type !== current.type) {
      this.toast.danger(`Type mismatch: file is "${parsed.type}", node is "${current.type}"`);
      return;
    }
    // Replacing selectedNode re-creates the editor form with the imported values;
    // nothing is persisted until the user presses Save.
    this.nodeStore.set('selectedNode', {
      ...current,
      config: parsed.config,
      ...(parsed.pose ? { pose: parsed.pose } : {}),
    });
    this.toast.success('Config imported — review and Save to apply');
  }
}
