import {Component, computed, inject, input, signal} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CanvasNode} from '../flow-canvas-node.component';
import {NodeStatusUpdate} from '../../../../../../core/models/node-status.model';
import {CalibrationApiService} from '../../../../../../core/services/api/calibration-api.service';
import {CalibrationNodeStatus} from '../../../../../../core/models/calibration.model';
import {ToastService} from '../../../../../../core/services/toast.service';

@Component({
  selector: 'app-node-calibration-controls',
  imports: [SynergyComponentsModule],
  templateUrl: './node-calibration-controls.html',
})
export class NodeCalibrationControls {
  node = input.required<CanvasNode>();
  status = input<NodeStatusUpdate | null>(null);
  protected calibrationStatus = computed(() => {
    return this.status() as CalibrationNodeStatus | null;
  });
  protected hasPendingCalibration = computed(() => {
    // In new status system, check application_state.value for calibration activity
    const appState = this.status()?.application_state;
    if (appState?.label === 'calibrating' && typeof appState.value === 'boolean') {
      return appState.value;
    }
    // Fallback to old CalibrationNodeStatus if still using legacy format
    return this.calibrationStatus()?.has_pending || false;
  });
  protected isCalibrating = signal<boolean>(false);
  protected calibrationError = signal<string | null>(null);
  private calibrationApi = inject(CalibrationApiService);
  private toast = inject(ToastService);

  protected async triggerCalibration(): Promise<void> {
    this.isCalibrating.set(true);
    this.calibrationError.set(null);

    try {
      const response = await this.calibrationApi.triggerCalibration(this.node().id);
      const resultCount = Object.keys(response.results || {}).length;

      if (resultCount === 0) {
        this.toast.warning(
          'No sensors to calibrate. Connect sensor nodes to the calibration node inputs and ensure they are running.',
        );
      } else if (response.pending_approval) {
        this.toast.success(`Calibration complete! ${resultCount} sensor(s) pending approval.`);
      } else {
        this.toast.success(`Calibration complete and auto-saved for ${resultCount} sensor(s).`);
      }
    } catch (error: any) {
      console.error('Failed to trigger calibration:', error);
      const errorMsg = error?.error?.detail || 'Calibration failed';
      this.calibrationError.set(errorMsg);
      this.toast.danger(`Calibration failed: ${errorMsg}`);
    } finally {
      this.isCalibrating.set(false);
    }
  }

  protected async acceptCalibration(): Promise<void> {
    this.isCalibrating.set(true);
    this.calibrationError.set(null);

    try {
      const response = await this.calibrationApi.acceptCalibration(this.node().id);
      const acceptedCount = response.accepted?.length || 0;

      this.toast.success(
        `Calibration accepted and saved for ${acceptedCount} sensor(s). Sensors will reload with new poses.`,
      );
    } catch (error: any) {
      console.error('Failed to accept calibration:', error);
      const errorMsg = error?.error?.detail || 'Failed to accept calibration';
      this.calibrationError.set(errorMsg);
      this.toast.danger(`Failed to accept: ${errorMsg}`);
    } finally {
      this.isCalibrating.set(false);
    }
  }

  protected async rejectCalibration(): Promise<void> {
    this.isCalibrating.set(true);

    try {
      await this.calibrationApi.rejectCalibration(this.node().id);
      this.toast.neutral('Calibration rejected. No changes were applied.');
    } catch (error: any) {
      console.error('Failed to reject calibration:', error);
      const errorMsg = error?.error?.detail || 'Failed to reject calibration';
      this.calibrationError.set(errorMsg);
      this.toast.danger(`Failed to reject: ${errorMsg}`);
    } finally {
      this.isCalibrating.set(false);
    }
  }
}
