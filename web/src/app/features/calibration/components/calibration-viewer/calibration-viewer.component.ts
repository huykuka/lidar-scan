import {Component, computed, effect, inject, signal} from '@angular/core';

import {ActivatedRoute, Router} from '@angular/router';
import {NodeStoreService} from '../../../../core/services/stores/node-store.service';
import {StatusWebSocketService} from '../../../../core/services/status-websocket.service';
import {CalibrationApiService} from '../../../../core/services/api/calibration-api.service';
import {ToastService} from '../../../../core/services/toast.service';
import {CalibrationNodeStatus,} from '../../../../core/models/calibration.model';
import {NodeConfig} from '../../../../core/models/node.model';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {ProcessingChainComponent} from '../processing-chain/processing-chain.component';
import {CalibrationAcceptDialogComponent} from '../calibration-accept-dialog/calibration-accept-dialog.component';
import {CalibrationRejectDialogComponent} from '../calibration-reject-dialog/calibration-reject-dialog.component';

@Component({
  selector: 'app-calibration-viewer',
  standalone: true,
  imports: [
    SynergyComponentsModule,
    ProcessingChainComponent,
    CalibrationAcceptDialogComponent,
    CalibrationRejectDialogComponent,
  ],
  templateUrl: './calibration-viewer.component.html',
})
export class CalibrationViewerComponent {
  nodeId = signal<string>('');
  isLoading = signal(false);
  isAccepting = signal(false);
  isRejecting = signal(false);
  runId = signal<string | null>(null);  // Track run ID from pending results

  // Dialog visibility signals
  showAcceptDialog = signal(false);
  showRejectDialog = signal(false);

  hasPendingResults = computed(() => {
    const node = this.calibrationNode();
    return (
      node?.has_pending && node.pending_results && Object.keys(node.pending_results).length > 0
    );
  });
  pendingResultsList = computed(() => {
    const node = this.calibrationNode();
    if (!node?.pending_results) return [];

    return Object.entries(node.pending_results).map(([sensorId, result]) => ({
      sensorId,
      ...result,
    }));
  });
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private nodeStore = inject(NodeStoreService);
  private statusWs = inject(StatusWebSocketService);
  calibrationNode = computed(() => {
    const statusResponse = this.statusWs.status();
    if (!statusResponse) return null;

    const node = statusResponse.nodes.find((n: any) => n.id === this.nodeId());
    return node && node.type === 'calibration' ? (node as unknown as CalibrationNodeStatus) : null;
  });
  private calibrationApi = inject(CalibrationApiService);
  private toast = inject(ToastService);

  constructor() {
    // Get node ID from route
    effect(
      () => {
        const params = this.route.snapshot.paramMap;
        const id = params.get('id');
        if (id) {
          this.nodeId.set(id);
        }
      },
      {allowSignalWrites: true},
    );
  }

  /**
   * Get buffered frame count (backward compatible with array and dict formats)
   */
  getBufferedFrameCount(bufferedFrames: Record<string, number> | string[]): number {
    if (Array.isArray(bufferedFrames)) {
      // Legacy array format
      return bufferedFrames.length;
    }
    // New dict format - return number of sensors
    return Object.keys(bufferedFrames).length;
  }

  /**
   * Get buffered frame entries for display
   */
  getBufferedFrameEntries(bufferedFrames: Record<string, number> | string[]): Array<{sensorId: string, count: number}> {
    if (Array.isArray(bufferedFrames)) {
      // Legacy array format - convert to entries with unknown count
      return bufferedFrames.map(sensorId => ({sensorId, count: 1}));
    }
    // New dict format
    return Object.entries(bufferedFrames).map(([sensorId, count]) => ({sensorId, count}));
  }

  getSensorName(sensorId: string): string {
    const nodes = this.nodeStore.nodes();
    const sensor = nodes.find((n: NodeConfig) => n.id === sensorId);
    return sensor?.name || 'Unknown Sensor';
  }

  getQualityVariant(quality: string): 'success' | 'warning' | 'danger' | 'neutral' {
    switch (quality) {
      case 'excellent':
        return 'success';
      case 'good':
        return 'warning';
      case 'fair':
        return 'warning';
      case 'poor':
        return 'danger';
      default:
        return 'neutral';
    }
  }

  formatDate(isoString: string): string {
    try {
      return new Date(isoString).toLocaleString();
    } catch {
      return isoString;
    }
  }

  /** Open the accept confirmation dialog */
  openAcceptDialog(): void {
    this.showAcceptDialog.set(true);
  }

  /** Open the reject confirmation dialog */
  openRejectDialog(): void {
    this.showRejectDialog.set(true);
  }

  /** Called by accept dialog with selected sensor IDs (null = accept all) */
  async acceptCalibration(sensorIds: string[] | null = null) {
    const node = this.calibrationNode();
    if (!node) return;

    this.showAcceptDialog.set(false);
    this.isAccepting.set(true);
    try {
      const request = sensorIds ? {sensor_ids: sensorIds} : {};
      const result = await this.calibrationApi.acceptCalibration(node.id, request);
      if (result.success) {
        const runIdMsg = result.run_id ? ` from run ${result.run_id.slice(0, 8)}` : '';
        const remainingMsg = result.remaining_pending && result.remaining_pending.length > 0
          ? ` ${result.remaining_pending.length} sensor(s) still pending.`
          : '';
        this.toast.success(
          `Calibration accepted for ${result.accepted.length} sensor(s)${runIdMsg}. Sensors will reload...${remainingMsg}`,
        );
        // Navigate back after short delay
        setTimeout(() => this.goBack(), 1500);
      }
    } catch (error: any) {
      this.toast.danger(`Failed to accept calibration: ${error.message}`);
    } finally {
      this.isAccepting.set(false);
    }
  }

  /** Called by reject dialog */
  async rejectCalibration() {
    const node = this.calibrationNode();
    if (!node) return;

    this.showRejectDialog.set(false);
    this.isRejecting.set(true);
    try {
      const result = await this.calibrationApi.rejectCalibration(node.id);
      if (result.success) {
        const rejectedCount = result.rejected?.length || 0;
        this.toast.neutral(
          `Calibration rejected for ${rejectedCount} sensor(s). No changes were applied.`
        );
      }
    } catch (error: any) {
      this.toast.danger(`Failed to reject calibration: ${error.message}`);
    } finally {
      this.isRejecting.set(false);
    }
  }

  viewHistory(): void {
    this.router.navigate(['/calibration', this.nodeId(), 'history']);
  }

  goBack() {
    this.router.navigate(['/calibration']);
  }
}

export class CalibrationViewerComponent {
  nodeId = signal<string>('');
  isLoading = signal(false);
  isAccepting = signal(false);
  isRejecting = signal(false);
  runId = signal<string | null>(null);  // NEW: Track run ID from pending results
  hasPendingResults = computed(() => {
    const node = this.calibrationNode();
    return (
      node?.has_pending && node.pending_results && Object.keys(node.pending_results).length > 0
    );
  });
  pendingResultsList = computed(() => {
    const node = this.calibrationNode();
    if (!node?.pending_results) return [];

    return Object.entries(node.pending_results).map(([sensorId, result]) => ({
      sensorId,
      ...result,
    }));
  });
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private nodeStore = inject(NodeStoreService);
  private statusWs = inject(StatusWebSocketService);
  calibrationNode = computed(() => {
    const statusResponse = this.statusWs.status();
    if (!statusResponse) return null;

    const node = statusResponse.nodes.find((n: any) => n.id === this.nodeId());
    return node && node.type === 'calibration' ? (node as unknown as CalibrationNodeStatus) : null;
  });
  private calibrationApi = inject(CalibrationApiService);
  private toast = inject(ToastService);

  constructor() {
    // Get node ID from route
    effect(
      () => {
        const params = this.route.snapshot.paramMap;
        const id = params.get('id');
        if (id) {
          this.nodeId.set(id);
        }
      },
      {allowSignalWrites: true},
    );
  }

  /**
   * Get buffered frame count (backward compatible with array and dict formats)
   */
  getBufferedFrameCount(bufferedFrames: Record<string, number> | string[]): number {
    if (Array.isArray(bufferedFrames)) {
      // Legacy array format
      return bufferedFrames.length;
    }
    // New dict format - return number of sensors
    return Object.keys(bufferedFrames).length;
  }

  /**
   * Get buffered frame entries for display
   */
  getBufferedFrameEntries(bufferedFrames: Record<string, number> | string[]): Array<{sensorId: string, count: number}> {
    if (Array.isArray(bufferedFrames)) {
      // Legacy array format - convert to entries with unknown count
      return bufferedFrames.map(sensorId => ({sensorId, count: 1}));
    }
    // New dict format
    return Object.entries(bufferedFrames).map(([sensorId, count]) => ({sensorId, count}));
  }

  getSensorName(sensorId: string): string {
    const nodes = this.nodeStore.nodes();
    const sensor = nodes.find((n: NodeConfig) => n.id === sensorId);
    return sensor?.name || 'Unknown Sensor';
  }

  getQualityVariant(quality: string): 'success' | 'warning' | 'danger' | 'neutral' {
    switch (quality) {
      case 'excellent':
        return 'success';
      case 'good':
        return 'warning';
      case 'fair':
        return 'warning';
      case 'poor':
        return 'danger';
      default:
        return 'neutral';
    }
  }

  formatDate(isoString: string): string {
    try {
      return new Date(isoString).toLocaleString();
    } catch {
      return isoString;
    }
  }

  async acceptCalibration() {
    const node = this.calibrationNode();
    if (!node) return;

    this.isAccepting.set(true);
    try {
      const result = await this.calibrationApi.acceptCalibration(node.id);
      if (result.success) {
        const runIdMsg = result.run_id ? ` from run ${result.run_id.slice(0, 8)}` : '';
        const remainingMsg = result.remaining_pending && result.remaining_pending.length > 0
          ? ` ${result.remaining_pending.length} sensor(s) still pending.`
          : '';
        this.toast.success(
          `Calibration accepted for ${result.accepted.length} sensor(s)${runIdMsg}. Sensors will reload...${remainingMsg}`,
        );
        // Navigate back after short delay
        setTimeout(() => this.goBack(), 1500);
      }
    } catch (error: any) {
      this.toast.danger(`Failed to accept calibration: ${error.message}`);
    } finally {
      this.isAccepting.set(false);
    }
  }

  async rejectCalibration() {
    const node = this.calibrationNode();
    if (!node) return;

    this.isRejecting.set(true);
    try {
      const result = await this.calibrationApi.rejectCalibration(node.id);
      if (result.success) {
        const rejectedCount = result.rejected?.length || 0;
        this.toast.neutral(
          `Calibration rejected for ${rejectedCount} sensor(s). No changes were applied.`
        );
      }
    } catch (error: any) {
      this.toast.danger(`Failed to reject calibration: ${error.message}`);
    } finally {
      this.isRejecting.set(false);
    }
  }

  goBack() {
    this.router.navigate(['/calibration']);
  }
}
