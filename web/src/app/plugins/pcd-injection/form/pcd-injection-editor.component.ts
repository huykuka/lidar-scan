import {Component, computed, effect, inject, OnDestroy, output, signal} from '@angular/core';
import {FormBuilder, FormGroup, ReactiveFormsModule, Validators} from '@angular/forms';
import {SynergyComponentsModule, SynergyFormsModule} from '@synergy-design-system/angular';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {NodeEditorFacadeService} from '@features/settings/services/node-editor-facade.service';
import {NodeEditorComponent} from '@core/models/node-plugin.model';
import {NodeEditorHeaderComponent} from '@plugins/shared/node-editor-header/node-editor-header.component';

@Component({
  selector: 'app-pcd-injection-editor',
  standalone: true,
  imports: [ReactiveFormsModule, SynergyComponentsModule, SynergyFormsModule, NodeEditorHeaderComponent],
  providers: [NodeEditorFacadeService],
  templateUrl: './pcd-injection-editor.component.html',
  styleUrl: './pcd-injection-editor.component.css',
})
export class PcdInjectionEditorComponent implements NodeEditorComponent, OnDestroy {
  saved = output<void>();
  cancelled = output<void>();
  protected isSaving = signal(false);
  protected form!: FormGroup;
  protected isSaveDisabled = computed(() => this.form?.invalid || this.isSaving());
  private fb = inject(FormBuilder);
  private nodeStore = inject(NodeStoreService);
  protected definition = computed(() => {
    const data = this.nodeStore.selectedNode();
    return this.nodeStore.nodeDefinitions().find((d) => d.type === data.type);
  });
  private facade = inject(NodeEditorFacadeService);

  constructor() {
    effect(() => {
      const def = this.definition();
      if (def) {
        this.initForm();
      }
    });
  }

  ngOnDestroy() {}

  async onSave() {
    if (this.form.invalid) return;

    const def = this.definition();
    if (!def) return;

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

  onCancel() {
    this.cancelled.emit();
  }

  private initForm() {
    const data = this.nodeStore.selectedNode();

    this.form = this.fb.group({
      name: [data.name || 'PCD Injection', [Validators.required]],
    });
  }
}
