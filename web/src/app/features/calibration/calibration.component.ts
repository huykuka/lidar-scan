import {Component, computed, effect, inject, OnInit} from '@angular/core';
import {KeyValuePipe} from '@angular/common';
import {Router} from '@angular/router';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CalibrationStoreService} from '../../core/services/stores/calibration-store.service';
import {NodeStoreService} from '../../core/services/stores/node-store.service';
import {ToastService} from '../../core/services/toast.service';
import {NavigationService} from '../../core/services';
import {CalibrationNodeStatusResponse} from '../../core/models/calibration.model';
import {ProcessingChainComponent} from './components/processing-chain/processing-chain.component';

@Component({
  selector: 'app-calibration',
  standalone: true,
  imports: [SynergyComponentsModule, KeyValuePipe, ProcessingChainComponent],
  templateUrl: './calibration.component.html',
})
export class CalibrationComponent implements OnInit {
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

  constructor() {
    this.navigationService.setPageConfig({
      title: 'Calibration',
      subtitle: 'Manage and monitor calibration nodes',
    });

    // Show error toasts from store
    effect(() => {
      const error = this.calibrationStore.error();
      if (error) this.toast.danger(error);
    });
  }

  ngOnInit(): void {
    // Note: startPolling stops the previous poll when a new one starts.
    // For multiple calibration nodes, we poll each in sequence — the last one
    // will be the "active" polled node. Consider upgrading to per-node polling
    // if the app regularly has >1 calibration node.
    const nodes = this.calibrationNodeConfigs();
    for (const node of nodes) {
      this.calibrationStore.startPolling(node.id);
    }
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
