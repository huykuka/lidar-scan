import { Component, computed, inject, output, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { SynergyComponentsModule, SynergyFormsModule } from '@synergy-design-system/angular';
import { NodeEditorComponent } from '@core/models/node-plugin.model';
import { NodeStoreService } from '@core/services/stores/node-store.service';
import { ToastService } from '@core/services/toast.service';
import { NodeEditorHeaderComponent } from '@plugins/shared/node-editor-header/node-editor-header.component';
import { NodeEditorFacadeService } from '@features/settings/services/node-editor-facade.service';

/**
 * Editor component for configuring Result Storage nodes.
 * Exposes the two backend properties: default_status (select) and status_key (string).
 */
@Component({
  selector: 'app-result-storage-editor',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    SynergyComponentsModule,
    SynergyFormsModule,
    NodeEditorHeaderComponent,
  ],
  providers: [NodeEditorFacadeService],
  templateUrl: './result-storage-editor.component.html',
  styleUrl: './result-storage-editor.component.css',
})
export class ResultStorageEditorComponent implements NodeEditorComponent {
  saved = output<void>();
  cancelled = output<void>();

  private nodeStore = inject(NodeStoreService);
  private toast = inject(ToastService);
  private facade = inject(NodeEditorFacadeService);

  form!: FormGroup;
  protected isSaving = signal(false);

  protected definition = computed(() =>
    this.nodeStore.nodeDefinitions().find((d) => d.type === 'result_storage')
  );

  protected isEditMode = computed(() => this.nodeStore.select('editMode')());

  protected statusOptions = [
    { label: 'Success', value: 'success' },
    { label: 'Warning', value: 'warning' },
    { label: 'Error', value: 'error' },
  ];

  constructor() {
    const node = this.nodeStore.selectedNode();

    this.form = new FormGroup({
      name: new FormControl(node?.name || 'Result Storage', [Validators.required]),
      default_status: new FormControl(
        node?.config?.['default_status'] ?? 'success',
        [Validators.required]
      ),
      status_key: new FormControl(
        node?.config?.['status_key'] ?? ''
      ),
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
      config: {
        default_status: this.form.value.default_status ?? 'success',
        status_key: this.form.value.status_key ?? '',
      },
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
}
