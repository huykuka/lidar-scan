import { Component, computed, effect, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { NodeStoreService } from '../../../../core/services/stores/node-store.service';
import { StatusWebSocketService } from '../../../../core/services/status-websocket.service';
import { CalibrationApiService } from '../../../../core/services/api/calibration-api.service';
import { ToastService } from '../../../../core/services/toast.service';
import {
  CalibrationNodeStatus,
  CalibrationResult,
} from '../../../../core/models/calibration.model';
import { NodeConfig } from '../../../../core/models/node.model';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

@Component({
  selector: 'app-calibration-viewer',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './calibration-viewer.component.html',
})
export class CalibrationViewerComponent {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private nodeStore = inject(NodeStoreService);
  private statusWs = inject(StatusWebSocketService);
  private calibrationApi = inject(CalibrationApiService);
  private toast = inject(ToastService);

  nodeId = signal<string>('');
  isLoading = signal(false);
  isAccepting = signal(false);
  isRejecting = signal(false);

  calibrationNode = computed(() => {
    const statusResponse = this.statusWs.status();
    if (!statusResponse) return null;
    
    const node = statusResponse.nodes.find((n: any) => n.id === this.nodeId());
    return node && node.type === 'calibration' ? (node as unknown as CalibrationNodeStatus) : null;
  });

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
      { allowSignalWrites: true },
    );
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
        this.toast.success(
          `Calibration accepted for ${result.accepted.length} sensor(s). Sensors will reload...`,
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
        this.toast.neutral('Calibration rejected. No changes were applied.');
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
