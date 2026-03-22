import {Component, computed, effect, inject, OnDestroy, signal} from '@angular/core';
import {toSignal} from '@angular/core/rxjs-interop';
import {KeyValuePipe} from '@angular/common';
import {ActivatedRoute, Router} from '@angular/router';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CalibrationStoreService} from '../../../../core/services/stores/calibration-store.service';
import {NodeStoreService} from '../../../../core/services/stores/node-store.service';
import {NavigationService} from '../../../../core/services/navigation.service';
import {ToastService} from '../../../../core/services/toast.service';
import {
  CalibrationHistoryRecord,
  CalibrationNodeStatusResponse,
  PendingCalibrationResult,
  PoseDelta,
} from '../../../../core/models/calibration.model';
import {NodeConfig} from '../../../../core/models/node.model';
import {ProcessingChainComponent} from '../processing-chain/processing-chain.component';

@Component({
  selector: 'app-calibration-viewer',
  standalone: true,
  imports: [
    SynergyComponentsModule,
    KeyValuePipe,
    ProcessingChainComponent,
  ],
  templateUrl: './calibration-viewer.component.html',
})
export class CalibrationViewerComponent implements OnDestroy {
  // ── Dependencies ─────────────────────────────────────────────────────────
  private readonly calibrationStore = inject(CalibrationStoreService);
  private readonly nodeStore = inject(NodeStoreService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);
  private readonly navigationService = inject(NavigationService);

  // ── Route param as a reactive signal ─────────────────────────────────────
  // Using toSignal(route.paramMap) ensures this re-evaluates on direct
  // navigation and after a cold page reload — not just once at construction.
  private readonly _routeParamMap = toSignal(this.route.paramMap);

  nodeId = computed<string | null>(() => this._routeParamMap()?.get('id') ?? null);

  // ── Store pass-throughs ───────────────────────────────────────────────────
  isTriggering = this.calibrationStore.isTriggering;
  isAccepting = this.calibrationStore.isAccepting;
  isRejecting = this.calibrationStore.isRejecting;
  isRollingBack = this.calibrationStore.isRollingBack;
  isLoadingStatus = this.calibrationStore.isLoadingStatus;

  // ── Derived signals ───────────────────────────────────────────────────────
  calibrationNode = computed<CalibrationNodeStatusResponse | null>(() =>
    this.calibrationStore.getNodeStatus()(this.nodeId() ?? ''),
  );

  pendingResultEntries = computed(() => {
    const node = this.calibrationNode();
    if (!node) return [];
    return Object.entries(node.pending_results);
  });

  historyForNode = computed(() =>
    this.calibrationStore.getHistoryForNode()(this.nodeId() ?? ''),
  );

  /**
   * True when "Run Calibration" should be disabled.
   * ICP requires a reference sensor + at least 1 source sensor.
   * Disabled only when source_sensor_ids is empty (no source to calibrate against reference).
   */
  isCalibrationDisabled = computed<boolean>(() => {
    const node = this.calibrationNode();
    if (!node) return false; // not loaded yet — optimistic
    return node.source_sensor_ids.length < 1;
  });

  /** Tooltip shown when the calibration trigger button is disabled. */
  readonly calibrationDisabledTooltip =
    'At least 1 source sensor is required. Connect a sensor upstream in the DAG.';

  /** True when at least one history record exists for the current node. */
  hasHistory = computed<boolean>(() => this.historyForNode().length > 0);

  // ── UI state ──────────────────────────────────────────────────────────────
  showMatrixFor = signal<Record<string, boolean>>({});

  constructor() {
    // Reactive effect: fires immediately on construction AND whenever nodeId()
    // changes (e.g. the user navigates to a different calibration node, or the
    // app is cold-reloaded directly to /calibration/:id).
    effect(
      () => {
        const id = this.nodeId();
        if (id) {
          this.calibrationStore.startPolling(id);
          this.navigationService.setPageConfig({
            title: 'Calibration',
            subtitle: `Node: ${id}`,
          });
        }
      },
      {allowSignalWrites: true},
    );

    // Load history once node status resolves and source_sensor_ids are known.
    // Re-runs whenever calibrationNode() changes (e.g. after polling picks up new sensors).
    effect(() => {
      const id = this.nodeId();
      const node = this.calibrationNode();
      if (id && node && node.source_sensor_ids.length > 0) {
        void this.calibrationStore.loadHistoryForNode(id);
      }
    });

    // Update title when node name is resolved from the API
    effect(() => {
      const node = this.calibrationNode();
      if (node?.node_name) {
        this.navigationService.setPageConfig({
          title: node.node_name,
          subtitle: `Node: ${node.node_id}`,
        });
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

  // ── Helper methods ────────────────────────────────────────────────────────

  computePoseDelta(result: PendingCalibrationResult): PoseDelta {
    return {
      dx: result.pose_after.x - result.pose_before.x,
      dy: result.pose_after.y - result.pose_before.y,
      dz: result.pose_after.z - result.pose_before.z,
      droll: result.pose_after.roll - result.pose_before.roll,
      dpitch: result.pose_after.pitch - result.pose_before.pitch,
      dyaw: result.pose_after.yaw - result.pose_before.yaw,
    };
  }
  

  getSensorName(sensorId: string): string {
    const nodes = this.nodeStore.nodes();
    const sensor = nodes.find((n: NodeConfig) => n.id === sensorId);
    return sensor?.name || sensorId;
  }

  formatDate(isoString: string | null | undefined): string {
    if (!isoString) return '—';
    try {
      return new Date(isoString).toLocaleString();
    } catch {
      return isoString;
    }
  }

  getQualityVariant(quality: string): 'success' | 'warning' | 'danger' | 'neutral' {
    switch (quality) {
      case 'excellent': return 'success';
      case 'good': return 'warning';
      case 'poor': return 'danger';
      default: return 'neutral';
    }
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  async triggerCalibration(): Promise<void> {
    const nodeId = this.nodeId();
    if (!nodeId) return;
    await this.calibrationStore.triggerCalibration(nodeId, {});
  }

  async acceptCalibration(): Promise<void> {
    const nodeId = this.nodeId();
    if (!nodeId) return;
    await this.calibrationStore.acceptCalibration(nodeId, {sensor_ids: undefined});
    void this.calibrationStore.loadHistoryForNode(nodeId);
  }

  async rejectCalibration(): Promise<void> {
    const nodeId = this.nodeId();
    if (!nodeId) return;
    await this.calibrationStore.rejectCalibration(nodeId);
    void this.calibrationStore.loadHistoryForNode(nodeId);
  }

  async rollbackToEntry(record: CalibrationHistoryRecord): Promise<void> {
    const nodeId = this.nodeId();
    const sensorId = record.source_sensor_id ?? record.sensor_id;
    await this.calibrationStore.rollbackHistory(sensorId, record.id);
    if (nodeId) void this.calibrationStore.loadHistoryForNode(nodeId);
  }

  // ── Navigation ────────────────────────────────────────────────────────────

  viewHistory(): void {
    void this.router.navigate(['/calibration', this.nodeId(), 'history']);
  }

  goBack(): void {
    void this.router.navigate(['/calibration']);
  }
}
