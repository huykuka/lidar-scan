import { Component, computed, inject, output, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule, SynergyFormsModule } from '@synergy-design-system/angular';
import { NodeEditorComponent } from '@core/models/node-plugin.model';
import { NodeStoreService } from '@core/services/stores/node-store.service';
import { ToastService } from '@core/services/toast.service';
import { NodeEditorHeaderComponent } from '@plugins/shared/node-editor-header/node-editor-header.component';
import { NodeEditorFacadeService } from '@features/settings/services/node-editor-facade.service';
import { environment } from '@env/environment';

/**
 * Editor component for configuring Snapshot Nodes.
 * Provides editable throttle_ms with validation, and displays the full
 * HTTP POST trigger endpoint (using environment.apiUrl) with a copy-to-clipboard button —
 * matching the UX pattern of the IfCondition editor.
 */
@Component({
  selector: 'app-snapshot-node-editor',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    CommonModule,
    SynergyComponentsModule,
    SynergyFormsModule,
    NodeEditorHeaderComponent,
  ],
  providers: [NodeEditorFacadeService],
  templateUrl: './snapshot-node-editor.component.html',
  styleUrl: './snapshot-node-editor.component.css',
})
export class SnapshotNodeEditorComponent implements NodeEditorComponent {
  saved = output<void>();
  cancelled = output<void>();

  private nodeStore = inject(NodeStoreService);
  private toast = inject(ToastService);
  private facade = inject(NodeEditorFacadeService);

  form!: FormGroup;
  protected isSaving = signal(false);

  /**
   * Node definition for the 'snapshot' type
   */
  protected definition = computed(() =>
    this.nodeStore.nodeDefinitions().find((d) => d.type === 'snapshot')
  );

  /**
   * Whether we are editing an existing (already-saved) node
   */
  protected isEditMode = computed(() => this.nodeStore.select('editMode')());

  /**
   * Current node ID — null when creating a brand-new node
   */
  protected nodeId = computed(() => this.nodeStore.selectedNode()?.id ?? null);

  /**
   * Full dynamic HTTP POST trigger endpoint using environment.apiUrl.
   * Matches the construction pattern used in IfConditionEditorComponent.
   */
  protected triggerUrl = computed(() =>
    this.nodeId()
      ? `${environment.apiUrl}/nodes/${this.nodeId()}/trigger`
      : null
  );

  constructor() {
    const node = this.nodeStore.selectedNode();

    this.form = new FormGroup({
      name: new FormControl(node?.name || 'Snapshot Node', [Validators.required]),
      throttle_ms: new FormControl(
        node?.config?.['throttle_ms'] ?? 0,
        [Validators.required, Validators.min(0)]
      ),
    });
  }

  /**
   * Save the node via the facade service
   */
  async onSave(): Promise<void> {
    if (!this.form.valid) {
      this.toast.warning('Please fix validation errors before saving');
      return;
    }

    const def = this.definition();
    if (!def) {
      this.toast.danger('Node definition not found');
      return;
    }

    this.isSaving.set(true);

    const success = await this.facade.saveNode({
      name: this.form.value.name,
      config: {
        throttle_ms: this.form.value.throttle_ms ?? 0,
      },
      definition: def,
      existingNode: this.nodeStore.selectedNode(),
    });

    this.isSaving.set(false);

    if (success) {
      this.saved.emit();
    }
  }

  /**
   * Cancel editing
   */
  onCancel(): void {
    this.cancelled.emit();
  }

  /**
   * Copy text to clipboard with toast feedback — same pattern as IfConditionEditorComponent
   */
  protected copyToClipboard(text: string): Promise<void> {
    return navigator.clipboard
      .writeText(text)
      .then(() => {
        this.toast.success('URL copied to clipboard');
      })
      .catch((err) => {
        console.error('Failed to copy to clipboard:', err);
        this.toast.danger('Failed to copy to clipboard');
      });
  }
}
