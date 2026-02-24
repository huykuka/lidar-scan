import { Component, Output, EventEmitter, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators, AbstractControl, ValidationErrors } from '@angular/forms';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarStoreService } from '../../../../core/services/stores/lidar-store.service';
import { LidarApiService } from '../../../../core/services/api/lidar-api.service';
import { DialogService } from '../../../../core/services';
import { ToastService } from '../../../../core/services/toast.service';

@Component({
  selector: 'app-lidar-editor',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, SynergyComponentsModule],
  templateUrl: './lidar-editor.html',
  styleUrl: './lidar-editor.css',
})
export class LidarEditorComponent implements OnInit {
  private fb = inject(FormBuilder);
  protected lidarStore = inject(LidarStoreService);
  private lidarApi = inject(LidarApiService);
  private dialogService = inject(DialogService);
  private toast = inject(ToastService);

  @Output() save = new EventEmitter<any>();

  protected form!: FormGroup;
  protected pipelines = this.lidarStore.availablePipelines;

  private slugify(val: string): string {
    const base = (val || '').trim().replace(/[^A-Za-z0-9_-]+/g, '_');
    return base.replace(/_+/g, '_').replace(/^[_-]+|[_-]+$/g, '') || 'sensor';
  }

  protected topicHelpText(): string {
    const prefix = this.slugify(this.form?.get('topic_prefix')?.value || this.form?.get('name')?.value || 'sensor');
    return `Topics: ${prefix}_raw_points, ${prefix}_processed_points`;
  }

  /**
   * Calculate the next available IMU UDP port.
   * Starts from 7501 and increments to avoid collisions.
   */
  private calculateNextImuUdpPort(currentLidarId?: string): number {
    const allLidars = this.lidarStore.lidars();
    const usedPorts = new Set<number>();

    // Extract all currently used IMU UDP ports
    allLidars.forEach((lidar) => {
      // Skip the current lidar being edited
      if (currentLidarId && lidar.id === currentLidarId) {
        return;
      }

      const args = lidar.launch_args || '';
      const imuPortMatch = args.match(/imu_udp_port:=(\d+)/);
      if (imuPortMatch) {
        usedPorts.add(parseInt(imuPortMatch[1]));
      }
    });

    // Find next available port starting from 7501
    let port = 7501;
    while (usedPorts.has(port)) {
      port++;
    }

    return port;
  }

  /**
   * Custom validator to check if IMU UDP port is already used by another sensor.
   */
  private imuPortDuplicateValidator(control: AbstractControl): ValidationErrors | null {
    if (!control.value) {
      return null;
    }

    const port = parseInt(control.value);
    const currentLidarId = this.form?.getRawValue().id;
    const allLidars = this.lidarStore.lidars();

    // Check if port is used by another sensor
    const isDuplicate = allLidars.some((lidar) => {
      // Skip the current lidar being edited
      if (currentLidarId && lidar.id === currentLidarId) {
        return false;
      }

      const args = lidar.launch_args || '';
      const imuPortMatch = args.match(/imu_udp_port:=(\d+)/);
      if (imuPortMatch) {
        return parseInt(imuPortMatch[1]) === port;
      }
      return false;
    });

    return isDuplicate ? { duplicate: { value: port } } : null;
  }

  ngOnInit() {
    this.initForm();
  }

  private initForm() {
    const lidar = this.lidarStore.selectedLidar();
    const isEdit = !!lidar?.id;
    const pose = lidar?.pose || { x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0 };

    // Parse launch args
    const args = lidar?.launch_args || '';
    const hostMatch = args.match(/hostname:=([\d\.]+)/);
    const receiverMatch = args.match(/udp_receiver_ip:=([\d\.]+)/);
    const portMatch = args.match(/udp_port:=(\d+)/);
    const imuPortMatch = args.match(/imu_udp_port:=(\d+)/);

    const ipPattern = /^(\d{1,3}\.){3}\d{1,3}$/;

    // Calculate next available IMU UDP port if creating new sensor
    const nextImuPort = this.calculateNextImuUdpPort(lidar?.id);

    this.form = this.fb.group({
      id: [{ value: lidar?.id || '', disabled: isEdit }],
      name: [lidar?.name || '', [Validators.required]],
      topic_prefix: [lidar?.topic_prefix || this.slugify(lidar?.name || '')],
      mode: [lidar?.mode || 'real'],
      pipeline_name: [lidar?.pipeline_name === 'none' ? '' : lidar?.pipeline_name || ''],
      pcd_path: [lidar?.pcd_path || ''],
      // Launch Params
      hostname: [hostMatch ? hostMatch[1] : '192.168.1.123', [Validators.pattern(ipPattern)]],
      udp_receiver_ip: [
        receiverMatch ? receiverMatch[1] : '192.168.1.89',
        [Validators.pattern(ipPattern)],
      ],
      udp_port: [
        portMatch ? parseInt(portMatch[1]) : 2666,
        [Validators.min(1), Validators.max(65535)],
      ],
      imu_udp_port: [
        imuPortMatch ? parseInt(imuPortMatch[1]) : nextImuPort,
        [Validators.min(1), Validators.max(65535)],
      ],
      // Pose
      x: [pose.x || 0],
      y: [pose.y || 0],
      z: [pose.z || 0],
      roll: [pose.roll || 0],
      pitch: [pose.pitch || 0],
      yaw: [pose.yaw || 0],
    });

    // Update validators based on mode
    this.form.get('mode')?.valueChanges.subscribe((mode) => {
      this.updateValidators(mode);
    });
    this.updateValidators(this.form.get('mode')?.value).updateValueAndValidity();

    // If user hasn't touched topic_prefix, keep it aligned with name.
    this.form.get('name')?.valueChanges.subscribe((name) => {
      const ctrl = this.form.get('topic_prefix');
      if (!ctrl || ctrl.dirty) return;
      ctrl.setValue(this.slugify(name || ''));
    });

    // Add custom validator for imu_udp_port to check duplicates
    this.form.get('imu_udp_port')?.addValidators(this.imuPortDuplicateValidator.bind(this));
  }

  private updateValidators(mode: string) {
    const pcdPathCtrl = this.form.get('pcd_path');
    const hostnameCtrl = this.form.get('hostname');
    const receiverCtrl = this.form.get('udp_receiver_ip');
    const portCtrl = this.form.get('udp_port');
    const imuPortCtrl = this.form.get('imu_udp_port');

    if (mode === 'sim') {
      pcdPathCtrl?.setValidators([Validators.required]);
      hostnameCtrl?.clearValidators();
      receiverCtrl?.clearValidators();
      portCtrl?.clearValidators();
      imuPortCtrl?.clearValidators();
    } else {
      pcdPathCtrl?.clearValidators();
      const ipPattern = /^(\d{1,3}\.){3}\d{1,3}$/;
      hostnameCtrl?.setValidators([Validators.required, Validators.pattern(ipPattern)]);
      receiverCtrl?.setValidators([Validators.required, Validators.pattern(ipPattern)]);
      portCtrl?.setValidators([Validators.required, Validators.min(1), Validators.max(65535)]);
      imuPortCtrl?.setValidators([
        Validators.required,
        Validators.min(1),
        Validators.max(65535),
        this.imuPortDuplicateValidator.bind(this),
      ]);
    }

    pcdPathCtrl?.updateValueAndValidity();
    hostnameCtrl?.updateValueAndValidity();
    receiverCtrl?.updateValueAndValidity();
    portCtrl?.updateValueAndValidity();
    imuPortCtrl?.updateValueAndValidity();
    return this.form;
  }

  protected async onSave() {
    if (this.form.invalid) return;

    const val = this.form.getRawValue();
    let launch_args = '';

    if (val.mode === 'real') {
      launch_args = `./launch/sick_multiscan.launch hostname:=${val.hostname} udp_receiver_ip:=${val.udp_receiver_ip} udp_port:=${val.udp_port} imu_udp_port:=${val.imu_udp_port}`;
    }

    const payload = {
      id: val.id || undefined,
      name: val.name,
      topic_prefix: val.topic_prefix || undefined,
      mode: val.mode,
      pipeline_name: val.pipeline_name || null,
      launch_args: launch_args,
      pcd_path: val.pcd_path,
      x: val.x,
      y: val.y,
      z: val.z,
      roll: val.roll,
      pitch: val.pitch,
      yaw: val.yaw,
    };

    try {
      await this.lidarApi.saveLidar(payload);
      await this.lidarApi.reloadConfig();
      await this.lidarApi.getLidars();
      this.save.emit(payload);
      this.dialogService.close();
    } catch (error) {
      console.error('Failed to save lidar', error);
      this.toast.danger('Failed to save LiDAR configuration.');
    }
  }

  protected onCancel() {
    this.dialogService.close();
  }
}
