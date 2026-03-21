import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReactiveFormsModule } from '@angular/forms';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { PoseFormComponent } from './pose-form.component';
import { Pose, ZERO_POSE } from '@core/models/pose.model';

describe('PoseFormComponent', () => {
  let component: PoseFormComponent;
  let fixture: ComponentFixture<PoseFormComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PoseFormComponent, ReactiveFormsModule],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(PoseFormComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('Form initialization', () => {
    it('should initialize form with ZERO_POSE by default', () => {
      expect(component.poseFormGroup.value).toEqual(ZERO_POSE);
    });

    it('should expose 6 form controls: x, y, z, roll, pitch, yaw', () => {
      const controls = ['x', 'y', 'z', 'roll', 'pitch', 'yaw'];
      controls.forEach(name => {
        expect(component.poseFormGroup.get(name)).toBeTruthy();
      });
    });
  });

  describe('resetPose()', () => {
    it('should reset all 6 form values to zero', () => {
      component.poseFormGroup.patchValue({ x: 100, y: 200, z: 300, roll: 45, pitch: -30, yaw: 90 });
      component.resetPose();
      expect(component.poseFormGroup.value).toEqual(ZERO_POSE);
    });

    it('should emit poseChange with ZERO_POSE when resetPose() is called', () => {
      const emitted: Pose[] = [];
      component.poseChange.subscribe((p: Pose) => emitted.push(p));

      component.poseFormGroup.patchValue({ x: 50, y: 0, z: 0, roll: 10, pitch: 0, yaw: 0 });
      component.resetPose();

      expect(emitted.length).toBe(1);
      expect(emitted[0]).toEqual(ZERO_POSE);
    });
  });

  describe('onRangeInput()', () => {
    it('should patch the form control and emit poseChange when synInputEvent fires for roll', () => {
      const emitted: Pose[] = [];
      component.poseChange.subscribe((p: Pose) => emitted.push(p));

      const fakeEvent = { target: { value: '45' } } as unknown as Event;
      component.onRangeInput('roll', fakeEvent);

      expect(component.poseFormGroup.get('roll')?.value).toBe(45);
      expect(emitted.length).toBe(1);
      expect(emitted[0].roll).toBe(45);
    });

    it('should patch pitch control', () => {
      const fakeEvent = { target: { value: '-30' } } as unknown as Event;
      component.onRangeInput('pitch', fakeEvent);
      expect(component.poseFormGroup.get('pitch')?.value).toBe(-30);
    });

    it('should patch yaw control', () => {
      const fakeEvent = { target: { value: '180' } } as unknown as Event;
      component.onRangeInput('yaw', fakeEvent);
      expect(component.poseFormGroup.get('yaw')?.value).toBe(180);
    });

    it('should set NaN on invalid string input (browser range always emits numeric, but guard is NaN)', () => {
      const fakeEvent = { target: { value: 'abc' } } as unknown as Event;
      component.onRangeInput('roll', fakeEvent);
      // NaN means the control has NaN which triggers invalid state
      const value = component.poseFormGroup.get('roll')?.value;
      expect(isNaN(value)).toBe(true);
    });
  });

  describe('onRangeChange()', () => {
    it('should mark the roll control as dirty when synChangeEvent fires', () => {
      const rollControl = component.poseFormGroup.get('roll')!;
      expect(rollControl.dirty).toBe(false);

      const fakeEvent = {} as Event;
      component.onRangeChange('roll', fakeEvent);

      expect(rollControl.dirty).toBe(true);
    });
  });

  describe('Validation — angleRangeValidator', () => {
    it('should be INVALID when roll > 180', () => {
      component.poseFormGroup.get('roll')?.setValue(181);
      expect(component.poseFormGroup.get('roll')?.valid).toBe(false);
      expect(component.poseFormGroup.get('roll')?.errors?.['angleRange']).toBeTruthy();
    });

    it('should be INVALID when roll < -180', () => {
      component.poseFormGroup.get('roll')?.setValue(-181);
      expect(component.poseFormGroup.get('roll')?.valid).toBe(false);
      expect(component.poseFormGroup.get('roll')?.errors?.['angleRange']).toBeTruthy();
    });

    it('should be VALID at exactly 180', () => {
      component.poseFormGroup.get('roll')?.setValue(180);
      expect(component.poseFormGroup.get('roll')?.valid).toBe(true);
    });

    it('should be VALID at exactly -180', () => {
      component.poseFormGroup.get('roll')?.setValue(-180);
      expect(component.poseFormGroup.get('roll')?.valid).toBe(true);
    });

    it('should be VALID for pitch within range', () => {
      component.poseFormGroup.get('pitch')?.setValue(-5);
      expect(component.poseFormGroup.get('pitch')?.valid).toBe(true);
    });

    it('should be INVALID for yaw out of range (270)', () => {
      component.poseFormGroup.get('yaw')?.setValue(270);
      expect(component.poseFormGroup.get('yaw')?.valid).toBe(false);
    });
  });

  describe('isValid getter', () => {
    it('should return true when all form controls are valid', () => {
      expect(component.isValid).toBe(true);
    });

    it('should return false when any angle control is invalid', () => {
      component.poseFormGroup.get('roll')?.setValue(270);
      expect(component.isValid).toBe(false);
    });
  });

  describe('Input signal → form sync', () => {
    it('should sync form when pose input changes', async () => {
      const newPose: Pose = { x: 100, y: 200, z: 300, roll: 10, pitch: 20, yaw: 30 };
      fixture.componentRef.setInput('pose', newPose);
      await fixture.whenStable();
      fixture.detectChanges();

      expect(component.poseFormGroup.get('x')?.value).toBe(100);
      expect(component.poseFormGroup.get('roll')?.value).toBe(10);
    });
  });

  describe('angleLabelFn', () => {
    it('should format angle as degrees string', () => {
      expect(component.angleLabelFn(45)).toBe('45°');
      expect(component.angleLabelFn(-90)).toBe('-90°');
      expect(component.angleLabelFn(0)).toBe('0°');
    });
  });
});
