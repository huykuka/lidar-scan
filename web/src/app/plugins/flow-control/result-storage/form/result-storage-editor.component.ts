import { Component, computed, inject, output, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { SynergyComponentsModule, SynergyFormsModule } from '@synergy-design-system/angular';
import { NodeEditorComponent } from '@core/models/node-plugin.model';
import { NodeStoreService } from '@core/services/stores/node-store.service';
import { ToastService } from '@core/services/toast.service';
import { NodeEditorHeaderComponent } from '@plugins/shared/node-editor-header/node-editor-header.component';
import { NodeEditorFacadeService } from '@features/settings/services/node-editor-facade.service';

const DEFAULT_COLOR = '#9E9E9E';

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
  changeDetection: ChangeDetectionStrategy.Eager,
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
  protected colorControl = new FormControl(DEFAULT_COLOR, { nonNullable: true });

  protected definition = computed(() =>
    this.nodeStore.nodeDefinitions().find((d) => d.type === 'result_storage')
  );

  protected isEditMode = computed(() => this.nodeStore.select('editMode')());

  constructor() {
    const node = this.nodeStore.selectedNode();
    const savedColor: string = node?.config?.['pcd_color'] ?? DEFAULT_COLOR;

    this.form = new FormGroup({
      name: new FormControl(node?.name || 'Result Storage', [Validators.required]),
    });

    this.colorControl.setValue(savedColor);
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
        pcd_color: this.colorControl.value,
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
