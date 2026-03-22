import {Component, computed, input, output, signal} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CalibrationHistoryRecord} from '@core/models';

/**
 * Smart component: displays calibration history records with provenance metadata.
 * Supports filtering by source_sensor_id and run_id.
 * Backward compatible with legacy records (null provenance fields).
 */
@Component({
  selector: 'app-calibration-history-table',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './calibration-history-table.component.html',
})
export class CalibrationHistoryTableComponent {
  /** All history records to display */
  records = input.required<CalibrationHistoryRecord[]>();

  /** Emits when user clicks a run_id to filter by it */
  filterByRunId = output<string>();

  /** Emits when user wants to view a record detail */
  viewDetail = output<CalibrationHistoryRecord>();

  // --- Filter signals ---
  filterSourceSensor = signal<string>('');
  filterRunId = signal<string>('');

  /** Unique source sensor IDs for the filter dropdown */
  uniqueSourceSensors = computed(() => {
    const ids = new Set<string>();
    for (const r of this.records()) {
      if (r.source_sensor_id) ids.add(r.source_sensor_id);
    }
    return Array.from(ids);
  });

  /** Filtered + sorted records */
  filteredRecords = computed(() => {
    let result = this.records();

    const sensorFilter = this.filterSourceSensor().trim();
    if (sensorFilter) {
      result = result.filter(
        (r) => r.source_sensor_id === sensorFilter,
      );
    }

    const runIdFilter = this.filterRunId().trim();
    if (runIdFilter) {
      result = result.filter(
        (r) => r.run_id === runIdFilter,
      );
    }

    // Sort newest first
    return [...result].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    );
  });

  /** Whether any filter is active */
  hasActiveFilters = computed(() =>
    !!this.filterSourceSensor() || !!this.filterRunId(),
  );

  onSourceSensorFilterChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.filterSourceSensor.set(value);
  }

  onRunIdFilterInput(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.filterRunId.set(value);
  }

  clearFilters(): void {
    this.filterSourceSensor.set('');
    this.filterRunId.set('');
  }

  onRunIdClick(runId: string): void {
    this.filterRunId.set(runId);
    this.filterByRunId.emit(runId);
  }

  onViewDetail(record: CalibrationHistoryRecord): void {
    this.viewDetail.emit(record);
  }

  isLegacyRecord(record: CalibrationHistoryRecord): boolean {
    return !record.run_id && !record.source_sensor_id;
  }

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

  shortId(id: string | null | undefined): string {
    if (!id) return '—';
    return id.length > 12 ? id.slice(0, 8) + '…' : id;
  }

  getChainLength(record: CalibrationHistoryRecord): number {
    return (record.processing_chain ?? []).length;
  }
}
