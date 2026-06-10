import { Component, computed, inject, output, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { SynergyComponentsModule, SynergyFormsModule } from '@synergy-design-system/angular';
import { NodeEditorComponent } from '@core/models/node-plugin.model';
import { NodeStoreService } from '@core/services/stores/node-store.service';
import { ToastService } from '@core/services/toast.service';
import { NodeEditorHeaderComponent } from '@plugins/shared/node-editor-header/node-editor-header.component';
import { NodeEditorFacadeService } from '@features/settings/services/node-editor-facade.service';

/** Default PCD label colors matching the backend PCD_LABEL_COLORS. */
const DEFAULT_COLORS: Record<string, string> = {
  empty: '#2196F3',
  loaded: '#F44336',
  merged: '#4CAF50',
};
const DEFAULT_COLOR = '#9E9E9E';

interface ColorEntry {
  label: FormControl<string>;
  color: FormControl<string>;
}

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
  protected colorEntries = signal<FormGroup<ColorEntry>[]>([]);

  protected definition = computed(() =>
    this.nodeStore.nodeDefinitions().find((d) => d.type === 'result_storage')
  );

  protected isEditMode = computed(() => this.nodeStore.select('editMode')());

  constructor() {
    const node = this.nodeStore.selectedNode();
    const colorMap: Record<string, string> = node?.config?.['color_map'] ?? {};

    this.form = new FormGroup({
      name: new FormControl(node?.name || 'Result Storage', [Validators.required]),
    });

    // Initialize color entries from saved config
    const entries: FormGroup<ColorEntry>[] = [];
    for (const [label, color] of Object.entries(colorMap)) {
      entries.push(this._createColorEntry(label, color));
    }
    this.colorEntries.set(entries);
  }

  addColorEntry(): void {
    const entries = [...this.colorEntries()];
    entries.push(this._createColorEntry('', DEFAULT_COLOR));
    this.colorEntries.set(entries);
  }

  removeColorEntry(index: number): void {
    const entries = [...this.colorEntries()];
    entries.splice(index, 1);
    this.colorEntries.set(entries);
  }

  /** Returns the default color for a well-known label, or the generic default. */
  getDefaultColor(label: string): string {
    return DEFAULT_COLORS[label.toLowerCase()] ?? DEFAULT_COLOR;
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

    // Build color_map from entries
    const colorMap: Record<string, string> = {};
    for (const entry of this.colorEntries()) {
      const label = entry.controls.label.value.trim();
      const color = entry.controls.color.value;
      if (label) {
        colorMap[label] = color;
      }
    }

    this.isSaving.set(true);

    const success = await this.facade.saveNode({
      name: this.form.value.name,
      config: {
        color_map: colorMap,
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

  private _createColorEntry(label: string, color: string): FormGroup<ColorEntry> {
    return new FormGroup<ColorEntry>({
      label: new FormControl(label, { nonNullable: true, validators: [Validators.required] }),
      color: new FormControl(color, { nonNullable: true }),
    });
  }
}
