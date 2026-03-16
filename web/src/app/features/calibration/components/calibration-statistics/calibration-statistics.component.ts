import {Component, computed, input, output} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CalibrationHistoryRecord, CalibrationStatistics} from '../../../../core/models/calibration.model';

export interface RunSummary {
  runId: string;
  sensorCount: number;
  acceptedCount: number;
  avgFitness: number | null;
}

export interface SourceSensorStats {
  sourceSensorId: string;
  attempts: number;
  acceptedCount: number;
  avgFitness: number | null;
  avgChainLength: number;
}

/**
 * Presentation component: shows calibration statistics with provenance breakdowns.
 * Displays by-source-sensor histogram, processing chain complexity, and run correlation.
 */
@Component({
  selector: 'app-calibration-statistics',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './calibration-statistics.component.html',
})
export class CalibrationStatisticsComponent {
  /** Base statistics from API */
  statistics = input<CalibrationStatistics | null>(null);

  /** All history records for provenance breakdowns */
  historyRecords = input<CalibrationHistoryRecord[]>([]);

  /** Emits when user wants to filter by run ID */
  filterByRun = output<string>();

  /** Per-source-sensor statistics */
  bySensor = computed<SourceSensorStats[]>(() => {
    const records = this.historyRecords();
    const map = new Map<string, {
      attempts: number;
      accepted: number;
      fitnessSum: number;
      fitnessCount: number;
      chainLengthSum: number;
    }>();

    for (const r of records) {
      const key = r.source_sensor_id ?? '__legacy__';
      const existing = map.get(key) ?? {
        attempts: 0, accepted: 0, fitnessSum: 0, fitnessCount: 0, chainLengthSum: 0,
      };
      existing.attempts++;
      if (r.accepted) existing.accepted++;
      if (r.fitness != null) { existing.fitnessSum += r.fitness; existing.fitnessCount++; }
      existing.chainLengthSum += (r.processing_chain ?? []).length;
      map.set(key, existing);
    }

    return Array.from(map.entries())
      .map(([id, stats]) => ({
        sourceSensorId: id,
        attempts: stats.attempts,
        acceptedCount: stats.accepted,
        avgFitness: stats.fitnessCount > 0 ? stats.fitnessSum / stats.fitnessCount : null,
        avgChainLength: stats.attempts > 0 ? stats.chainLengthSum / stats.attempts : 0,
      }))
      .sort((a, b) => b.attempts - a.attempts);
  });

  /** Recent calibration runs grouped by run_id */
  recentRuns = computed<RunSummary[]>(() => {
    const records = this.historyRecords();
    const map = new Map<string, { sensors: Set<string>; accepted: number; fitnessSum: number; fitnessCount: number }>();

    for (const r of records) {
      if (!r.run_id) continue;
      const existing = map.get(r.run_id) ?? { sensors: new Set(), accepted: 0, fitnessSum: 0, fitnessCount: 0 };
      existing.sensors.add(r.sensor_id);
      if (r.accepted) existing.accepted++;
      if (r.fitness != null) { existing.fitnessSum += r.fitness; existing.fitnessCount++; }
      map.set(r.run_id, existing);
    }

    return Array.from(map.entries())
      .map(([runId, stats]) => ({
        runId,
        sensorCount: stats.sensors.size,
        acceptedCount: stats.accepted,
        avgFitness: stats.fitnessCount > 0 ? stats.fitnessSum / stats.fitnessCount : null,
      }))
      .slice(0, 10); // Show last 10 runs
  });

  /** Average processing chain length across all new-format records */
  avgChainLength = computed(() => {
    const records = this.historyRecords().filter((r) => (r.processing_chain ?? []).length > 0);
    if (records.length === 0) return null;
    const total = records.reduce((sum, r) => sum + (r.processing_chain ?? []).length, 0);
    return (total / records.length).toFixed(1);
  });

  /** Count of legacy records */
  legacyCount = computed(() =>
    this.historyRecords().filter((r) => !r.run_id && !r.source_sensor_id).length,
  );

  onFilterByRun(runId: string): void {
    this.filterByRun.emit(runId);
  }

  getRunStatusVariant(run: RunSummary): 'success' | 'warning' | 'neutral' {
    if (run.acceptedCount === run.sensorCount) return 'success';
    if (run.acceptedCount > 0) return 'warning';
    return 'neutral';
  }

  getRunLabel(run: RunSummary): string {
    if (run.acceptedCount === run.sensorCount) return 'All accepted';
    if (run.acceptedCount > 0) return `${run.acceptedCount}/${run.sensorCount} accepted`;
    return 'Not accepted';
  }
}

