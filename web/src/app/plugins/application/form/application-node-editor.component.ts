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
  selector: 'app-application-node-editor',
  standalone: true,
  imports: [ReactiveFormsModule, SynergyComponentsModule, NodeEditorHeaderComponent],
  providers: [NodeEditorFacadeService],
  templateUrl: './application-node-editor.component.html',
  styleUrl: './application-node-editor.component.css',
})
export class ApplicationNodeEditorComponent implements NodeEditorComponent, OnDestroy {
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
  protected sensorNodeOptions = computed(() => {
    const nodes = this.nodeStore.nodes();
    return nodes
      .filter((n) => n.category === 'sensor')
      .map((n) => ({label: n.name || n.id, value: n.id}));
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
    if (prop.options_source === 'sensor_nodes') {
      return this.sensorNodeOptions();
    }
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

        if (prop.type === 'vec3') {
          configGroup[prop.name] = this.fb.group({
            0: [val ? val[0] : prop.default ? prop.default[0] : 0],
            1: [val ? val[1] : prop.default ? prop.default[1] : 0],
            2: [val ? val[2] : prop.default ? prop.default[2] : 0],
          });
        } else {
          configGroup[prop.name] = [
            val ?? prop.default,
            prop.required ? [Validators.required] : [],
          ];
        }
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
