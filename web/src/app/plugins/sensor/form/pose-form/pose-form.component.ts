import {
  AbstractControl,
  FormBuilder,
  FormGroup,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  effect,
  inject,
  input,
  OnInit,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {UpperCasePipe} from '@angular/common';
import {SynergyComponentsModule, SynergyFormsModule} from '@synergy-design-system/angular';
import {Pose, ZERO_POSE} from '@core/models/pose.model';
import { NodesApiService } from '@core/services/api';
import { filter } from 'rxjs';

/**
 * Conversion factor: backend stores position in meters,
 * the form displays position in millimeters.
 */
const M_TO_MM = 1000;
const MM_TO_M = 1 / M_TO_MM;

/** Validates that a numeric value is within the [-180, +180] degree range. */
export function angleRangeValidator(control: AbstractControl): ValidationErrors | null {
  const v = control.value;
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  if (isNaN(n) || n < -180 || n > 180) {
    return { angleRange: { min: -180, max: 180, actual: v } };
  }
  return null;
}

@Component({
  selector: 'app-pose-form',
  imports: [ReactiveFormsModule, SynergyComponentsModule, UpperCasePipe, SynergyFormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './pose-form.component.html',
})
export class PoseFormComponent implements OnInit {
  /**
   * Current pose value — syncs from parent via signal input.
   * Position values (x, y, z) are in **meters** (backend unit).
   */
  pose = input<Pose>(ZERO_POSE);

  /**
   * Emitted whenever any pose value changes (slider drag, input, or reset).
   * Position values (x, y, z) are emitted in **meters** (backend unit).
   */
  poseChange = output<Pose>();
  poseValidChange = output<boolean>();

  /**
   * Node id used for one-shot floor calibration. When null/empty the
   * "Calibrate from Floor" button is hidden (e.g. for unsaved nodes).
   */
  nodeId = input<string | null>(null);

  /** When true, floor calibration is disabled (IMU auto-level owns leveling). */
  imuAutoLevel = input<boolean>(false);

  poseFormGroup!: FormGroup;

  protected isCalibratingFloor = signal(false);
  protected floorCalibrationMessage = signal<string | null>(null);

  private fb = inject(FormBuilder);
  private destroyRef = inject(DestroyRef);
  private nodesApi = inject(NodesApiService);

  angleLabelFn = (value: number): string => `${value}°`;

  constructor() {
    effect(() => {
      const p = this.pose();
      if (this.poseFormGroup) {
        this.poseFormGroup.patchValue(this.poseToFormValue(p), { emitEvent: false });
      }
    });
  }

  ngOnInit(): void {
    const initial = this.poseToFormValue(this.pose());
    this.poseFormGroup = this.fb.group({
      x: [initial.x, [Validators.required]],
      y: [initial.y, [Validators.required]],
      z: [initial.z, [Validators.required]],
      roll: [initial.roll, [Validators.required, angleRangeValidator]],
      pitch: [initial.pitch, [Validators.required, angleRangeValidator]],
      yaw: [initial.yaw, [Validators.required, angleRangeValidator]],
    });
    this.poseFormGroup.valueChanges
      .pipe(
        filter(() => this.poseFormGroup.valid),
        filter(
          (raw) =>
            !['x', 'y', 'z', 'roll', 'pitch', 'yaw'].some((k) => {
              const s = String(raw[k] ?? '');
              return s === '-' || s.endsWith('.');
            }),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.poseChange.emit(this.formValueToPose(this.poseFormGroup.getRawValue()));
      });

    this.poseFormGroup.statusChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((status) => {
        this.poseValidChange.emit(status === 'VALID');
      });
  }

  get isValid(): boolean {
    return this.poseFormGroup?.valid ?? true;
  }

  resetPose(): void {
    this.poseFormGroup.patchValue(this.poseToFormValue(ZERO_POSE));
    this.poseChange.emit({ ...ZERO_POSE });
  }

  async onCalibrateFromFloor(): Promise<void> {
    const id = this.nodeId();
    if (!id) return;

    this.isCalibratingFloor.set(true);
    this.floorCalibrationMessage.set(null);

    try {
      const result = await this.nodesApi.calibrateFromFloor(id);
      if (result.pose) {
        this.poseFormGroup.patchValue(this.poseToFormValue(result.pose), { emitEvent: false });
        this.poseChange.emit(result.pose);
        this.floorCalibrationMessage.set(
          `Applied: roll=${result.pose.roll.toFixed(2)}, pitch=${result.pose.pitch.toFixed(2)}`,
        );
      }
    } catch (err: any) {
      const detail = err?.error?.detail || err?.message || 'Floor calibration failed';
      this.floorCalibrationMessage.set(detail);
    } finally {
      this.isCalibratingFloor.set(false);
    }
  }

  private poseToFormValue(p: Pose): Pose {
    return {
      x: +(p.x * M_TO_MM).toFixed(3),
      y: +(p.y * M_TO_MM).toFixed(3),
      z: +(p.z * M_TO_MM).toFixed(3),
      roll: p.roll,
      pitch: p.pitch,
      yaw: p.yaw,
    };
  }

  private formValueToPose(raw: Record<string, any>): Pose {
    return {
      x: +(Number(raw['x']) * MM_TO_M).toFixed(6) || 0,
      y: +(Number(raw['y']) * MM_TO_M).toFixed(6) || 0,
      z: +(Number(raw['z']) * MM_TO_M).toFixed(6) || 0,
      roll: Number(raw['roll']) || 0,
      pitch: Number(raw['pitch']) || 0,
      yaw: Number(raw['yaw']) || 0,
    };
  }
}
