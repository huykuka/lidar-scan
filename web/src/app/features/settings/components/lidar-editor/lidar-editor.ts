import { Component, Output, EventEmitter, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarStoreService } from '../../../../core/services/stores/lidar-store.service';
import { LidarApiService } from '../../../../core/services/api/lidar-api.service';
import { DialogService } from '../../../../core/services';

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

  @Output() save = new EventEmitter<any>();

  protected form!: FormGroup;
  protected pipelines = this.lidarStore.availablePipelines;

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

    const ipPattern = /^(\d{1,3}\.){3}\d{1,3}$/;

    this.form = this.fb.group({
      id: [{ value: lidar?.id || '', disabled: isEdit }],
      name: [lidar?.name || '', [Validators.required]],
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
  }

  private updateValidators(mode: string) {
    const pcdPathCtrl = this.form.get('pcd_path');
    const hostnameCtrl = this.form.get('hostname');
    const receiverCtrl = this.form.get('udp_receiver_ip');
    const portCtrl = this.form.get('udp_port');

    if (mode === 'sim') {
      pcdPathCtrl?.setValidators([Validators.required]);
      hostnameCtrl?.clearValidators();
      receiverCtrl?.clearValidators();
      portCtrl?.clearValidators();
    } else {
      pcdPathCtrl?.clearValidators();
      const ipPattern = /^(\d{1,3}\.){3}\d{1,3}$/;
      hostnameCtrl?.setValidators([Validators.required, Validators.pattern(ipPattern)]);
      receiverCtrl?.setValidators([Validators.required, Validators.pattern(ipPattern)]);
      portCtrl?.setValidators([Validators.required, Validators.min(1), Validators.max(65535)]);
    }

    pcdPathCtrl?.updateValueAndValidity();
    hostnameCtrl?.updateValueAndValidity();
    receiverCtrl?.updateValueAndValidity();
    portCtrl?.updateValueAndValidity();
    return this.form;
  }

  protected async onSave() {
    if (this.form.invalid) return;

    const val = this.form.getRawValue();
    let launch_args = '';

    if (val.mode === 'real') {
      launch_args = `./launch/sick_multiscan.launch hostname:=${val.hostname} udp_receiver_ip:=${val.udp_receiver_ip} udp_port:=${val.udp_port}`;
    }

    const payload = {
      id: val.id || undefined,
      name: val.name,
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
      this.save.emit(payload);
      this.dialogService.close();
    } catch (error) {
      console.error('Failed to save lidar', error);
      alert('Failed to save lidar configuration');
    }
  }

  protected onCancel() {
    this.dialogService.close();
  }
}
