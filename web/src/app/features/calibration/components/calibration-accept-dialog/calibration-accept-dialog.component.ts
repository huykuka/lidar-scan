import {Component, computed, input, output, signal} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CalibrationNodeStatus} from '../../../../core/models/calibration.model';
import {ProcessingChainComponent} from '../processing-chain/processing-chain.component';

export interface PendingResultEntry {
  sensorId: string;
  fitness: number;
  rmse: number;
  quality: string;
  source_sensor_id?: string;
  processing_chain?: string[];
}

/**
 * Presentation dialog component: accept/reject confirmation with full provenance display.
 * Shows run_id, source sensors, processing chains, and allows selective sensor acceptance.
 */
@Component({
  selector: 'app-calibration-accept-dialog',
  standalone: true,
  imports: [SynergyComponentsModule, ProcessingChainComponent],
  templateUrl: './calibration-accept-dialog.component.html',
})
export class CalibrationAcceptDialogComponent {
  /** Whether the dialog is open */
  open = input<boolean>(false);

  /** The calibration node status with pending results */
  nodeStatus = input<CalibrationNodeStatus | null>(null);

  /** Run ID from the last calibration response */
  runId = input<string | null>(null);

  /** Whether accept is in progress */
  accepting = input<boolean>(false);

  /** Whether reject is in progress */
  rejecting = input<boolean>(false);

  /** Emits sensor IDs to accept (null = accept all) */
  accepted = output<string[] | null>();

  /** Emits when user confirms reject */
  rejected = output<void>();

  /** Emits when dialog is closed */
  closed = output<void>();

  /** Track selected sensor IDs for selective accept */
  selectedSensors = signal<Set<string>>(new Set());

  pendingResultsList = computed<PendingResultEntry[]>(() => {
    const node = this.nodeStatus();
    if (!node?.pending_results) return [];
    return Object.entries(node.pending_results).map(([sensorId, result]) => ({
      sensorId,
      ...result,
    }));
  });

  allSelected = computed(() => {
    const all = this.pendingResultsList().map((r) => r.sensorId);
    const sel = this.selectedSensors();
    return all.length > 0 && all.every((id) => sel.has(id));
  });

  constructor() {
    // Select all sensors by default when results change
    const updateSelection = () => {
      const all = this.pendingResultsList().map((r) => r.sensorId);
      this.selectedSensors.set(new Set(all));
    };
    // Initialize on first render
    setTimeout(updateSelection, 0);
  }

  toggleSensor(sensorId: string): void {
    const current = new Set(this.selectedSensors());
    if (current.has(sensorId)) {
      current.delete(sensorId);
    } else {
      current.add(sensorId);
    }
    this.selectedSensors.set(current);
  }

  toggleAll(): void {
    if (this.allSelected()) {
      this.selectedSensors.set(new Set());
    } else {
      this.selectedSensors.set(new Set(this.pendingResultsList().map((r) => r.sensorId)));
    }
  }

  isSensorSelected(sensorId: string): boolean {
    return this.selectedSensors().has(sensorId);
  }

  onAccept(): void {
    const selected = Array.from(this.selectedSensors());
    // If all sensors selected, pass null (accept all) for cleaner API call
    const allIds = this.pendingResultsList().map((r) => r.sensorId);
    const isAll = allIds.length === selected.length && allIds.every((id) => selected.includes(id));
    this.accepted.emit(isAll ? null : selected);
  }

  onReject(): void {
    this.rejected.emit();
  }

  onClose(): void {
    this.closed.emit();
  }

  getQualityVariant(quality: string | null | undefined): 'success' | 'warning' | 'danger' | 'neutral' {
    switch (quality) {
      case 'excellent': return 'success';
      case 'good': return 'warning';
      case 'poor': return 'danger';
      default: return 'neutral';
    }
  }

  shortRunId(runId: string | null | undefined): string {
    if (!runId) return '—';
    return runId.length > 8 ? runId.slice(0, 8) + '…' : runId;
  }

  shortId(id: string | null | undefined): string {
    if (!id) return '—';
    return id.length > 12 ? id.slice(0, 8) + '…' : id;
  }
}

