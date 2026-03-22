import {Component, computed, inject, input} from '@angular/core';
import {Router} from '@angular/router';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CanvasNode} from '../flow-canvas-node.component';
import {NodeStatusUpdate} from '../../../../../../core/models/node-status.model';
import {CalibrationNodeStatus} from '../../../../../../core/models/calibration.model';

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
    // Check application_state.value for calibration activity
    const appState = this.status()?.application_state;
    if (appState?.label === 'calibrating' && typeof appState.value === 'boolean') {
      return appState.value;
    }
    // Fallback to old CalibrationNodeStatus if still using legacy format
    return this.calibrationStatus()?.has_pending || false;
  });

  private router = inject(Router);

  navigateToCalibration(): void {
    void this.router.navigate(['/calibration', this.node().id]);
  }
}
