import { Component, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { StatusWebSocketService } from '../../core/services/status-websocket.service';
import { CalibrationNodeStatus } from '../../core/models/calibration.model';

@Component({
  selector: 'app-calibration',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './calibration.component.html',
})
export class CalibrationComponent {
  private statusWs = inject(StatusWebSocketService);
  private router = inject(Router);

  calibrationNodes = computed(() => {
    const statusResponse = this.statusWs.status();
    if (!statusResponse) return [];
    
    return statusResponse.nodes
      .filter((status: any) => status.type === 'calibration')
      .map((status: any) => status as unknown as CalibrationNodeStatus);
  });

  hasPendingResults(node: CalibrationNodeStatus): boolean {
    return node.pending_results && Object.keys(node.pending_results).length > 0;
  }

  getPendingResultsList(node: CalibrationNodeStatus) {
    if (!node.pending_results) return [];
    
    return Object.entries(node.pending_results).map(([sensorId, result]) => ({
      sensorId,
      ...result,
    }));
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

  formatTime(isoString: string): string {
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

  viewDetails(nodeId: string) {
    this.router.navigate(['/calibration', nodeId]);
  }

  viewHistory(nodeId: string) {
    this.router.navigate(['/calibration', nodeId, 'history']);
  }

  goToSettings() {
    this.router.navigate(['/settings']);
  }
}
