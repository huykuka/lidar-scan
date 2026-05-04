import {Component, computed, effect, inject, OnDestroy, output, signal} from '@angular/core';
import {FormBuilder, FormGroup, ReactiveFormsModule, Validators} from '@angular/forms';
import {Subscription} from 'rxjs';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {NodeEditorFacadeService} from '@features/settings/services/node-editor-facade.service';
import {NodeEditorComponent} from '@core/models/node-plugin.model';
import {NodeEditorHeaderComponent} from '@plugins/shared/node-editor-header/node-editor-header.component';
import {PropertySchema} from '@core/models/node.model';

@Component({
  selector: 'app-detection-node-editor',
  standalone: true,
  imports: [ReactiveFormsModule, SynergyComponentsModule, NodeEditorHeaderComponent],
  providers: [NodeEditorFacadeService],
  templateUrl: './detection-node-editor.component.html',
  styleUrl: './detection-node-editor.component.css',
})
export class DetectionNodeEditorComponent implements NodeEditorComponent, OnDestroy {
  saved = output<void>();
  cancelled = output<void>();
  protected isSaving = signal(false);
  protected form!: FormGroup;
  protected configForm!: FormGroup;
  private fb = inject(FormBuilder);
  private nodeStore = inject(NodeStoreService);
  protected definition = computed(() => {
    const data = this.nodeStore.selectedNode();
    return this.nodeStore.nodeDefinitions().find((d) => d.type === data.type);
  });
  private facade = inject(NodeEditorFacadeService);
  private formValues = signal<Record<string, any>>({});
  protected visibleProperties = computed(() => {
    const def = this.definition();
    if (!def) return [];
    const vals = this.formValues();
    return def.properties.filter((prop) => {
      if (prop.hidden) return false;
      if (prop.depends_on) {
        return Object.entries(prop.depends_on).every(([key, allowed]) =>
          (allowed as any[]).includes(vals[key]),
        );
      }
      return true;
    });
  });
  private formValuesSub?: Subscription;

  constructor() {
    effect(() => {
      const def = this.definition();
      if (def) {
        this.initForm();
      }
    });
  }

  ngOnDestroy() {
    this.formValuesSub?.unsubscribe();
  }

  async onSave() {
    if (this.form.invalid || this.configForm.invalid) return;

    const def = this.definition();
    if (!def) return;

    this.isSaving.set(true);

    const success = await this.facade.saveNode({
      name: this.form.value.name,
      config: this.configForm.getRawValue(),
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

  onSelectChange(propName: string, event: Event) {
    const value = (event.target as any).value;
    this.configForm.get(propName)?.setValue(value);
  }

  onCheckboxChange(propName: string, event: Event) {
    const checked = (event.target as any).checked;
    this.configForm.get(propName)?.setValue(checked);
  }

  getSelectOptions(prop: PropertySchema): {label: string; value: any}[] {
    return prop.options ?? [];
  }

  private initForm() {
    this.formValuesSub?.unsubscribe();

    const data = this.nodeStore.selectedNode();
    const def = this.definition();

    const configGroup: any = {};
    if (def) {
      def.properties.forEach((prop) => {
        const val = (data.config as any)?.[prop.name];
        configGroup[prop.name] = [
          val ?? prop.default,
          prop.required ? [Validators.required] : [],
        ];
      });
    }

    this.configForm = this.fb.group(configGroup);
    this.formValuesSub = this.configForm.valueChanges.subscribe((v) => this.formValues.set(v));
    this.formValues.set(this.configForm.getRawValue());

    this.form = this.fb.group({
      name: [data.name || def?.display_name || '', [Validators.required]],
    });
  }
}
