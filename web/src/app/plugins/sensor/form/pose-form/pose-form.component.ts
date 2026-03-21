import {
  AbstractControl,
  FormBuilder,
  FormGroup,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import {Component, effect, inject, input, OnInit, output,} from '@angular/core';
import {UpperCasePipe} from '@angular/common';
import {SynergyComponentsModule, SynergyFormsModule} from '@synergy-design-system/angular';
import {Pose, ZERO_POSE} from '@core/models/pose.model';

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
  standalone: true,

  imports: [ReactiveFormsModule, SynergyComponentsModule, UpperCasePipe,SynergyFormsModule],
  templateUrl: './pose-form.component.html',
})
export class PoseFormComponent implements OnInit {
  /** Current pose value — syncs from parent via signal input. */
  pose = input<Pose>(ZERO_POSE);

  /** Emitted whenever any pose value changes (slider drag, input, or reset). */
  poseChange = output<Pose>();

  poseFormGroup!: FormGroup;

  private fb = inject(FormBuilder);

  /** Tooltip formatter for syn-range: formats a number as "45°". */
  angleLabelFn = (value: number): string => `${value}°`;

  constructor() {
    effect(() => {
      const p = this.pose();
      if (this.poseFormGroup) {
        this.poseFormGroup.patchValue(p, { emitEvent: false });
      }
    });
  }

  ngOnInit(): void {
    const initial = this.pose();
    this.poseFormGroup = this.fb.group({
      x: [initial.x, [Validators.required]],
      y: [initial.y, [Validators.required]],
      z: [initial.z, [Validators.required]],
      roll: [initial.roll, [Validators.required, angleRangeValidator]],
      pitch: [initial.pitch, [Validators.required, angleRangeValidator]],
      yaw: [initial.yaw, [Validators.required, angleRangeValidator]],
    });
  }

  /** Exposes form validity for parent gate on save button. */
  get isValid(): boolean {
    return this.poseFormGroup?.valid ?? true;
  }

  /**
   * Handles numeric input for x, y, z fields.
   * Reads the input value, patches the form control.
   */
  onXyzInput(field: string, event: Event): void {
    const value = Number((event.target as HTMLInputElement).value);
    this.poseFormGroup.get(field)?.setValue(value);
    this.emitCurrentPose();
  }

  /**
   * Handles syn-input event for syn-range (live drag).
   * Patches the form, emits poseChange.
   */
  onRangeInput(field: 'roll' | 'pitch' | 'yaw', event: Event): void {
    const value = Number((event.target as any).value);
    this.poseFormGroup.get(field)?.setValue(value);
    this.emitCurrentPose();
  }

  /**
   * Handles syn-change event for syn-range (committed value).
   * Marks the field as dirty.
   */
  onRangeChange(field: 'roll' | 'pitch' | 'yaw', _event: Event): void {
    this.poseFormGroup.get(field)?.markAsDirty();
  }

  /** Resets all 6 controls to ZERO_POSE and emits poseChange. */
  resetPose(): void {
    this.poseFormGroup.patchValue(ZERO_POSE);
    this.poseChange.emit({ ...ZERO_POSE });
  }

  private emitCurrentPose(): void {
    const raw = this.poseFormGroup.getRawValue();
    this.poseChange.emit({
      x: Number(raw.x) || 0,
      y: Number(raw.y) || 0,
      z: Number(raw.z) || 0,
      roll: Number(raw.roll) || 0,
      pitch: Number(raw.pitch) || 0,
      yaw: Number(raw.yaw) || 0,
    });
  }
}
