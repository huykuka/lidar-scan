import {
  Component,
  inject,
  computed,
  signal,
  effect,
  output,
  CUSTOM_ELEMENTS_SCHEMA,
  OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Subscription } from 'rxjs';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeStoreService } from '../../../../core/services/stores/node-store.service';
import { LidarProfilesApiService } from '../../../../core/services/api/lidar-profiles-api';
import { NodeEditorFacadeService } from '../../services/node-editor-facade.service';
import { LidarTypeSelectComponent } from '../lidar-type-select/lidar-type-select.component';

@Component({
  selector: 'app-dynamic-node-editor',
  standalone: true,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [CommonModule, ReactiveFormsModule, SynergyComponentsModule, LidarTypeSelectComponent],
  providers: [NodeEditorFacadeService],
  templateUrl: './dynamic-node-editor.component.html',
  styleUrl: './dynamic-node-editor.component.css',
})
export class DynamicNodeEditorComponent implements OnDestroy {
  private fb = inject(FormBuilder);
  private nodeStore = inject(NodeStoreService);
  private lidarProfilesApi = inject(LidarProfilesApiService);
  private facade = inject(NodeEditorFacadeService);

  save = output<void>();
  cancel = output<void>();

  protected editMode = this.nodeStore.editMode;
  protected isSaving = signal(false);
  private formValues = signal<Record<string, any>>({});
  private formValuesSub?: Subscription;

  protected definition = computed(() => {
    const data = this.nodeStore.selectedNode();
    const type = data.type === 'operation' ? (data.config as any)?.op_type : data.type;
    return this.nodeStore.nodeDefinitions().find((d) => d.type === type);
  });

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

  protected form!: FormGroup;
  protected configForm!: FormGroup;

  constructor() {
    this.lidarProfilesApi.loadProfiles();

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

  private initForm() {
    this.formValuesSub?.unsubscribe();

    const data = this.nodeStore.selectedNode();
    const def = this.definition();

    const configGroup: any = {};
    if (def) {
      def.properties.forEach((prop) => {
        const currentConfig = data.config?.['op_config'] ?? data.config;
        const val = currentConfig ? currentConfig[prop.name] : prop.default;

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
      this.save.emit();
    }
  }

  onCancel() {
    this.cancel.emit();
  }

  onSelectChange(propName: string, event: Event) {
    const value = (event.target as any).value;
    this.configForm.get(propName)?.setValue(value);
  }

  onCheckboxChange(propName: string, event: Event) {
    const checked = (event.target as any).checked;
    this.configForm.get(propName)?.setValue(checked);
  }

  onLidarTypeChange(propName: string, value: string) {
    this.configForm.get(propName)?.setValue(value);
  }
}
