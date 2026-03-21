import {Component, computed, effect, inject, OnDestroy, output, signal} from '@angular/core';
import {FormBuilder, FormGroup, ReactiveFormsModule, Validators} from '@angular/forms';
import {Subscription} from 'rxjs';
import {SynergyComponentsModule, SynergyFormsModule} from '@synergy-design-system/angular';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {LidarProfilesApiService} from '@core/services/api/lidar-profiles-api.service';
import {NodeEditorFacadeService} from '@features/settings/services/node-editor-facade.service';
import {LidarTypeSelectComponent} from '@plugins/sensor/lidar-type-select/lidar-type-select.component';
import {NodeEditorComponent} from '@core/models/node-plugin.model';
import {NodeEditorHeaderComponent} from '@plugins/shared/node-editor-header/node-editor-header.component';
import {PoseFormComponent} from './pose-form/pose-form.component';
import {Pose, ZERO_POSE} from '@core/models/pose.model';

@Component({
  selector: 'app-sensor-node-editor',
  standalone: true,
  imports: [ReactiveFormsModule, SynergyComponentsModule, LidarTypeSelectComponent, NodeEditorHeaderComponent, PoseFormComponent,SynergyFormsModule],
  providers: [NodeEditorFacadeService],
  templateUrl: './sensor-node-editor.component.html',
  styleUrl: './sensor-node-editor.component.css',
})
export class SensorNodeEditorComponent implements NodeEditorComponent, OnDestroy {
  saved = output<void>();
  cancelled = output<void>();
  protected isSaving = signal(false);
  protected form!: FormGroup;
  protected configForm!: FormGroup;
  protected poseValue = signal<Pose>(ZERO_POSE);
  protected isPoseValid = signal<boolean>(true);
  protected isSaveDisabled = computed(
    () => this.form?.invalid || this.configForm?.invalid || !this.isPoseValid() || this.isSaving()
  );
  private fb = inject(FormBuilder);
  private nodeStore = inject(NodeStoreService);
  protected definition = computed(() => {
    const data = this.nodeStore.selectedNode();
    return this.nodeStore.nodeDefinitions().find((d) => d.type === data.type);
  });
  private lidarProfilesApi = inject(LidarProfilesApiService);
  private facade = inject(NodeEditorFacadeService);
  private formValues = signal<Record<string, any>>({});
  protected visibleProperties = computed(() => {
    const def = this.definition();
    if (!def) return [];
    const vals = this.formValues();
    return def.properties.filter((prop) => {
      if (prop.hidden) return false;
      if (prop.type === 'pose') return false;
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

  async onSave() {
    if (this.form.invalid || this.configForm.invalid || !this.isPoseValid()) return;

    const def = this.definition();
    if (!def) return;

    this.isSaving.set(true);

    const success = await this.facade.saveNode({
      name: this.form.value.name,
      config: this.configForm.getRawValue(),
      definition: def,
      existingNode: this.nodeStore.selectedNode(),
      pose: this.poseValue(),
    });

    this.isSaving.set(false);

    if (success) {
      this.saved.emit();
    }
  }

  onPoseChange(pose: Pose): void {
    this.poseValue.set(pose);
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

  onLidarTypeChange(propName: string, value: string) {
    this.configForm.get(propName)?.setValue(value);
  }

  private initForm() {
    this.formValuesSub?.unsubscribe();

    const data = this.nodeStore.selectedNode();
    const def = this.definition();

    // Initialize pose signal from node data
    this.poseValue.set(data.pose ?? ZERO_POSE);

    const configGroup: any = {};
    if (def) {
      def.properties.forEach((prop) => {
        if (prop.type === 'pose') return;
        const val = data.config ? data.config[prop.name] : prop.default;

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
