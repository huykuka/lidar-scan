import {Component, computed, inject, output, signal} from '@angular/core';
import {FormControl, FormGroup, ReactiveFormsModule, Validators} from '@angular/forms';
import {CommonModule} from '@angular/common';
import {SynergyComponentsModule, SynergyFormsModule} from '@synergy-design-system/angular';
import {NodeEditorComponent} from '@core/models/node-plugin.model';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {ToastService} from '@core/services/toast.service';
import {NodeEditorHeaderComponent} from '@plugins/shared/node-editor-header/node-editor-header.component';
import {NodeEditorFacadeService} from '@features/settings/services/node-editor-facade.service';
import {environment} from '@env/environment';

/**
 * Editor component for configuring PCD Injection Nodes.
 * Provides an editable name and displays the full HTTP POST upload endpoint
 * (using environment.apiUrl) with a copy-to-clipboard button —
 * matching the UX pattern of the Snapshot editor.
 */
@Component({
  selector: 'app-pcd-injection-editor',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    CommonModule,
    SynergyComponentsModule,
    SynergyFormsModule,
    NodeEditorHeaderComponent,
  ],
  providers: [NodeEditorFacadeService],
  templateUrl: './pcd-injection-editor.component.html',
  styleUrl: './pcd-injection-editor.component.css',
})
export class PcdInjectionEditorComponent implements NodeEditorComponent {
  saved = output<void>();
  cancelled = output<void>();

  private nodeStore = inject(NodeStoreService);
  private toast = inject(ToastService);
  private facade = inject(NodeEditorFacadeService);

  form!: FormGroup;
  protected isSaving = signal(false);

  protected definition = computed(() =>
    this.nodeStore.nodeDefinitions().find((d) => d.type === 'pcd_injection'),
  );

  protected isEditMode = computed(() => this.nodeStore.select('editMode')());

  protected nodeId = computed(() => this.nodeStore.selectedNode()?.id ?? null);

  /**
   * Full dynamic HTTP POST upload endpoint using environment.apiUrl.
   */
  protected uploadUrl = computed(() =>
    this.nodeId()
      ? `${environment.apiUrl}/pcd-injection/${this.nodeId()}/upload`
      : null,
  );

  constructor() {
    const node = this.nodeStore.selectedNode();

    this.form = new FormGroup({
      name: new FormControl(node?.name || 'PCD Injection', [Validators.required]),
    });
  }

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
      config: {},
      definition: def,
      existingNode: this.nodeStore.selectedNode(),
    });

    this.isSaving.set(false);

    if (success) {
      this.saved.emit();
    }
  }

  onCancel(): void {
    this.cancelled.emit();
  }

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
