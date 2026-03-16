import {Component, computed, effect, inject, signal} from '@angular/core';
import {ActivatedRoute, Router} from '@angular/router';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CalibrationApiService} from '../../../core/services/api/calibration-api.service';
import {NavigationService} from '../../../core/services';
import {
  CalibrationHistoryRecord,
  CalibrationHistoryResponse,
  CalibrationStatistics,
} from '../../../core/models/calibration.model';
import {CalibrationHistoryTableComponent} from '../components/calibration-history-table/calibration-history-table.component';
import {CalibrationHistoryDetailComponent} from '../components/calibration-history-detail/calibration-history-detail.component';
import {CalibrationStatisticsComponent} from '../components/calibration-statistics/calibration-statistics.component';

type TabId = 'history' | 'statistics';

/**
 * Smart page component: orchestrates history table, detail view, and statistics.
 * Reads nodeId from route params and run_id filter from query params.
 */
@Component({
  selector: 'app-calibration-history',
  standalone: true,
  imports: [
    SynergyComponentsModule,
    CalibrationHistoryTableComponent,
    CalibrationHistoryDetailComponent,
    CalibrationStatisticsComponent,
  ],
  templateUrl: './calibration-history.component.html',
})
export class CalibrationHistoryComponent {
  // --- Route state ---
  nodeId = signal<string>('');
  activeTab = signal<TabId>('history');

  // --- Loading / error state ---
  isLoading = signal(false);
  error = signal<string | null>(null);

  // --- Data signals ---
  historyRecords = signal<CalibrationHistoryRecord[]>([]);
  statistics = signal<CalibrationStatistics | null>(null);
  selectedRecord = signal<CalibrationHistoryRecord | null>(null);

  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private calibrationApi = inject(CalibrationApiService);
  private navigationService = inject(NavigationService);

  constructor() {
    // Extract nodeId from route params
    effect(
      () => {
        const id = this.route.snapshot.paramMap.get('id') ?? '';
        this.nodeId.set(id);
        this.navigationService.setPageConfig({
          title: 'Calibration History',
          subtitle: `Node: ${id.slice(0, 8)}`,
        });
        if (id) {
          // Check for run_id query param
          const runId = this.route.snapshot.queryParamMap.get('run_id') ?? undefined;
          this.loadHistory(id, undefined, runId);
          this.loadStatistics(id);
        }
      },
      {allowSignalWrites: true},
    );
  }

  async loadHistory(nodeId: string, sourceSensorId?: string, runId?: string): Promise<void> {
    this.isLoading.set(true);
    this.error.set(null);
    try {
      const response: CalibrationHistoryResponse = await this.calibrationApi.getHistory(
        nodeId, 50, sourceSensorId, runId,
      );
      this.historyRecords.set(response.history ?? []);
    } catch (e: any) {
      this.error.set(e?.error?.detail ?? 'Failed to load calibration history');
    } finally {
      this.isLoading.set(false);
    }
  }

  async loadStatistics(nodeId: string): Promise<void> {
    try {
      const stats = await this.calibrationApi.getStatistics(nodeId);
      this.statistics.set(stats);
    } catch {
      // Statistics are optional — don't block the page
    }
  }

  onFilterByRunId(runId: string): void {
    // Update URL query params so link is shareable
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {run_id: runId},
      queryParamsHandling: 'merge',
    });
    this.loadHistory(this.nodeId(), undefined, runId);
  }

  onViewDetail(record: CalibrationHistoryRecord): void {
    this.selectedRecord.set(record);
  }

  onCloseDetail(): void {
    this.selectedRecord.set(null);
  }

  onViewRun(runId: string): void {
    this.selectedRecord.set(null);
    this.onFilterByRunId(runId);
  }

  setTab(tab: TabId): void {
    this.activeTab.set(tab);
  }

  goBack(): void {
    this.router.navigate(['/calibration']);
  }
}

