import { Component, Output, EventEmitter, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { DialogService } from '../../../../core/services';
import { FusionStoreService } from '../../../../core/services/stores/fusion-store.service';
import { FusionApiService } from '../../../../core/services/api/fusion-api.service';
import { LidarStoreService } from '../../../../core/services/stores/lidar-store.service';
import { LidarApiService } from '../../../../core/services/api/lidar-api.service';
import { ToastService } from '../../../../core/services/toast.service';

@Component({
  selector: 'app-fusion-editor',
  imports: [CommonModule, ReactiveFormsModule, SynergyComponentsModule],
  templateUrl: './fusion-editor.html',
  styleUrl: './fusion-editor.css',
})
export class FusionEditorComponent implements OnInit {
  private fb = inject(FormBuilder);
  protected fusionStore = inject(FusionStoreService);
  protected lidarStore = inject(LidarStoreService);
  private fusionApi = inject(FusionApiService);
  private lidarApi = inject(LidarApiService);
  private dialogService = inject(DialogService);
  private toast = inject(ToastService);

  @Output() save = new EventEmitter<any>();

  protected form!: FormGroup;
  protected lidars = this.lidarStore.lidars;
  protected pipelines = this.lidarStore.availablePipelines;

  ngOnInit() {
    this.initForm();
  }

  private initForm() {
    const fusion = this.fusionStore.selectedFusion();
    const isEdit = !!fusion?.id;

    this.form = this.fb.group({
      id: [{ value: fusion?.id || '', disabled: isEdit }],
      name: [fusion?.name || '', [Validators.required]],
      topic: [fusion?.topic || 'fused_points', [Validators.required]],
      sensor_ids: [fusion?.sensor_ids || [], [Validators.required]],
      pipeline_name: [fusion?.pipeline_name || ''],
    });
  }

  protected get selectedSensors(): string[] {
    return this.form.get('sensor_ids')?.value || [];
  }

  protected toggleSensor(sensorId: string) {
    const sensors = new Set(this.selectedSensors);
    if (sensors.has(sensorId)) {
      sensors.delete(sensorId);
    } else {
      sensors.add(sensorId);
    }
    this.form.get('sensor_ids')?.setValue(Array.from(sensors));
  }

  protected async onSave() {
    if (this.form.invalid) return;

    const val = this.form.getRawValue();

    const payload = {
      id: val.id || undefined,
      name: val.name,
      topic: val.topic,
      sensor_ids: val.sensor_ids,
      pipeline_name: val.pipeline_name || null,
    };

    try {
      await this.fusionApi.saveFusion(payload);
      await this.lidarApi.reloadConfig();
      await Promise.all([this.lidarApi.getLidars(), this.fusionApi.getFusions()]);
      this.save.emit(payload);
      this.dialogService.close();
    } catch (error) {
      console.error('Failed to save fusion', error);
      this.toast.danger('Failed to save fusion configuration.');
    }
  }

  protected onCancel() {
    this.dialogService.close();
  }
}
