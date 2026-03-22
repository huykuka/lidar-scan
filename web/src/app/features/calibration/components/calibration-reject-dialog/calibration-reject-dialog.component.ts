import {Component, computed, input, output} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CalibrationNodeStatus} from '@core/models';

/**
 * Presentation dialog component: reject calibration confirmation.
 * Shows run_id, sensor count, and warns about discarding results.
 */
@Component({
  selector: 'app-calibration-reject-dialog',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './calibration-reject-dialog.component.html',
})
export class CalibrationRejectDialogComponent {
  /** Whether the dialog is open */
  open = input<boolean>(false);

  /** The calibration node status */
  nodeStatus = input<CalibrationNodeStatus | null>(null);

  /** Run ID from the last calibration response */
  runId = input<string | null>(null);

  /** Whether reject action is in progress */
  rejecting = input<boolean>(false);

  /** Emits when user confirms rejection */
  rejected = output<void>();

  /** Emits when dialog is closed without action */
  closed = output<void>();

  sensorCount = computed(() => {
    const node = this.nodeStatus();
    if (!node?.pending_results) return 0;
    return Object.keys(node.pending_results).length;
  });

  onReject(): void {
    this.rejected.emit();
  }

  onClose(): void {
    this.closed.emit();
  }
}

