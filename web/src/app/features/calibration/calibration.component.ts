import {Component, computed, effect, inject, OnDestroy} from '@angular/core';
import {KeyValuePipe} from '@angular/common';
import {Router} from '@angular/router';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CalibrationStoreService} from '../../core/services/stores/calibration-store.service';
import {NodeStoreService} from '../../core/services/stores/node-store.service';
import {ToastService} from '../../core/services/toast.service';
import {NavigationService} from '../../core/services';
import {CalibrationNodeStatusResponse} from '../../core/models/calibration.model';

/** Minimum number of source sensors required to run ICP calibration. */
const ICP_MIN_SOURCE_SENSORS = 2;

@Component({
  selector: 'app-calibration',
  standalone: true,
  imports: [SynergyComponentsModule, KeyValuePipe],
  templateUrl: './calibration.component.html',
})
export class CalibrationComponent implements OnDestroy {
  protected readonly calibrationStore = inject(CalibrationStoreService);
  private readonly nodeStore = inject(NodeStoreService);
  private readonly navigationService = inject(NavigationService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);

  // Calibration node configs from NodeStore (category === 'calibration')
  calibrationNodeConfigs = computed(() => this.nodeStore.calibrationNodes());

  // Factory: get polled status for a specific node
  getNodePolledStatus = computed(() => {
    const statuses = this.calibrationStore.nodeStatuses();
    return (nodeId: string): CalibrationNodeStatusResponse | null => statuses[nodeId] ?? null;
  });

  /**
   * Returns true when "Run Calibration" should be disabled for the given node.
   * ICP requires at least 2 source sensors. If polled status is not yet
   * available we fall back to allowing the button (we don't want to block
   * indefinitely just because the first poll hasn't returned yet).
   */
  isCalibrationDisabled = computed(() => {
    const statuses = this.calibrationStore.nodeStatuses();
    return (nodeId: string): boolean => {
      const status = statuses[nodeId];
      if (!status) return false; // Not yet loaded — allow (optimistic)
      return status.source_sensor_ids.length < ICP_MIN_SOURCE_SENSORS;
    };
  });

  /** Tooltip message shown when "Run Calibration" is disabled due to insufficient sensors. */
  readonly calibrationDisabledTooltip =
    'At least 2 input sensors are required for calibration.';

  /**
   * Returns true when "View History" should be shown for the given node.
   * The button is hidden when the history record list for that node is empty.
   */
  hasHistory = computed(() => {
    const historyByNode = this.calibrationStore.historyByNode();
    return (nodeId: string): boolean => (historyByNode[nodeId]?.length ?? 0) > 0;
  });

  constructor() {
    this.navigationService.setPageConfig({
      title: 'Calibration',
      subtitle: 'Manage and monitor calibration nodes',
    });

    // Reactive: start polling whenever calibrationNodeConfigs emits new values.
    // This covers cold page reloads where nodes may not be loaded at construction
    // time — the effect re-runs as soon as the NodeStore resolves its node list.
    effect(() => {
      const nodes = this.calibrationNodeConfigs();
      if (nodes.length === 0) return;
      // Note: startPolling cancels the previous poll before starting a new one.
      // For multiple calibration nodes, we poll each in sequence — the last one
      // will be the "active" polled node. Consider upgrading to per-node polling
      // if the app regularly has >1 calibration node.
      for (const node of nodes) {
        this.calibrationStore.startPolling(node.id);
      }
    });

    // Show error toasts from store
    effect(() => {
      const error = this.calibrationStore.error();
      if (error) this.toast.danger(error);
    });
  }

  ngOnDestroy(): void {
    this.calibrationStore.stopPolling();
  }

  async triggerCalibration(nodeId: string): Promise<void> {
    await this.calibrationStore.triggerCalibration(nodeId, {});
  }

  formatTime(isoString: string | null | undefined): string {
    if (!isoString) return '—';
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diff = now.getTime() - date.getTime();
      const minutes = Math.floor(diff / 60000);

      if (minutes < 1) return 'Just now';
      if (minutes < 60) return `${minutes}m ago`;
      const hours = Math.floor(minutes / 60);
      if (hours < 24) return `${hours}h ago`;
      const days = Math.floor(hours / 24);
      return `${days}d ago`;
    } catch {
      return isoString;
    }
  }

  viewDetails(nodeId: string): void {
    void this.router.navigate(['/calibration', nodeId]);
  }

  viewHistory(nodeId: string): void {
    void this.router.navigate(['/calibration', nodeId, 'history']);
  }

  goToSettings(): void {
    void this.router.navigate(['/settings']);
  }
}
