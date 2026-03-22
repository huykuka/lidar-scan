import {Component, computed, inject, input, output} from '@angular/core';
import {Router} from '@angular/router';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CalibrationHistoryRecord} from '@core/models';
import {NodeStoreService} from '../../../../core/services/stores/node-store.service';
import {NodeConfig} from '../../../../core/models/node.model';

/**
 * Presentation component: shows full detail for a single CalibrationHistoryRecord.
 * Displays provenance metadata (processing chain, source sensor, run ID) and pose data.
 */
@Component({
  selector: 'app-calibration-history-detail',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './calibration-history-detail.component.html',
})
export class CalibrationHistoryDetailComponent {
  /** The record to display */
  record = input.required<CalibrationHistoryRecord>();

  /** Whether a rollback operation is in progress */
  isRollingBack = input<boolean>(false);

  /** Emits the record.id when user requests rollback to this entry */
  rollback = output<string>();

  /** Emits when user clicks "View all in run" */
  viewRun = output<string>();

  /** Emits when user closes/goes back */
  close = output<void>();

  private readonly nodeStore = inject(NodeStoreService);
  private router = inject(Router);

  getSensorName(sensorId: string | null | undefined): string {
    if (!sensorId) return '—';
    const node = this.nodeStore.nodes().find((n: NodeConfig) => n.id === sensorId);
    return node?.name ?? sensorId;
  }

  isLegacyRecord = computed(() => {
    const r = this.record();
    return !r.run_id && !r.source_sensor_id;
  });

  processingChain = computed(() => this.record().processing_chain ?? []);

  getQualityVariant(quality: string | null | undefined): 'success' | 'warning' | 'danger' | 'neutral' {
    switch (quality) {
      case 'excellent': return 'success';
      case 'good': return 'warning';
      case 'poor': return 'danger';
      default: return 'neutral';
    }
  }

  formatDate(isoString: string): string {
    try {
      return new Date(isoString).toLocaleString();
    } catch {
      return isoString;
    }
  }

  formatPose(pose: any): string {
    if (!pose) return '—';
    return `x:${pose.x?.toFixed(3)} y:${pose.y?.toFixed(3)} z:${pose.z?.toFixed(3)} r:${pose.roll?.toFixed(3)} p:${pose.pitch?.toFixed(3)} y:${pose.yaw?.toFixed(3)}`;
  }

  onRollback(): void {
    this.rollback.emit(this.record().id);
  }

  onViewRun(runId: string): void {
    this.viewRun.emit(runId);
  }

  onClose(): void {
    this.close.emit();
  }
}

