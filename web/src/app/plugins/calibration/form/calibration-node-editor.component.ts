import {Component, CUSTOM_ELEMENTS_SCHEMA, OnDestroy, computed, effect, inject, output, signal} from '@angular/core';
import {FormBuilder, FormGroup, ReactiveFormsModule, Validators} from '@angular/forms';
import {Subscription} from 'rxjs';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {NodeEditorFacadeService} from '../../../features/settings/services/node-editor-facade.service';
import {NodeEditorComponent} from '@core/models/node-plugin.model';

@Component({
  selector: 'app-calibration-node-editor',
  standalone: true,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [ReactiveFormsModule, SynergyComponentsModule],
  providers: [NodeEditorFacadeService],
  templateUrl: './calibration-node-editor.component.html',
  styleUrl: './calibration-node-editor.component.css',
})
export class CalibrationNodeEditorComponent implements NodeEditorComponent, OnDestroy {
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

  protected availableSensors = computed(() => {
    return this.nodeStore.nodes().filter((n) => n.category === 'sensor');
  });

  protected selectedReferenceSensor = signal<string | null>(null);

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

  private initForm(): void {
    this.formValuesSub?.unsubscribe();

    const data = this.nodeStore.selectedNode();
    const def = this.definition();
    const config = data.config || {};

    this.form = this.fb.group({
      name: [data.name || def?.display_name || '', Validators.required],
    });

    const configGroup: any = {
      reference_sensor_id: [config['reference_sensor_id'] || null],
      sample_frames: [config['sample_frames'] || 10, [Validators.required, Validators.min(5), Validators.max(100)]],
    };

    if (def) {
      def.properties.forEach((prop) => {
        const val = config[prop.name];
        configGroup[prop.name] = [
          val ?? prop.default,
          prop.required ? [Validators.required] : [],
        ];
      });
    }

    this.configForm = this.fb.group(configGroup);
    this.formValuesSub = this.configForm.valueChanges.subscribe((v) => this.formValues.set(v));
    this.formValues.set(this.configForm.getRawValue());

    this.selectedReferenceSensor.set(config['reference_sensor_id'] || null);
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

  onReferenceSensorChange(event: any): void {
    const value = event.target.value;
    this.configForm.patchValue({reference_sensor_id: value || null});
    this.selectedReferenceSensor.set(value || null);
  }

  onSelectChange(propName: string, event: Event) {
    const value = (event.target as any).value;
    this.configForm.get(propName)?.setValue(value);
  }

  onCheckboxChange(propName: string, event: Event) {
    const checked = (event.target as any).checked;
    this.configForm.get(propName)?.setValue(checked);
  }
}
