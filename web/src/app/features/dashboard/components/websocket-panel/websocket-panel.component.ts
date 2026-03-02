import { Component, input, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynCardComponent, SynBadgeComponent } from '@synergy-design-system/angular';
import { WebSocketMetrics } from '../../../../core/models/metrics.model';

/**
 * Panel showing per-topic WebSocket streaming statistics
 * Displays connection counts, message rates, and bandwidth usage
 */
@Component({
  selector: 'app-websocket-panel',
  standalone: true,
  imports: [CommonModule, SynCardComponent, SynBadgeComponent],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './websocket-panel.component.html',
  styleUrl: './websocket-panel.component.css'
})
export class WebsocketPanelComponent {
  // Signal input
  wsMetrics = input<WebSocketMetrics | null>(null);

  getTopicEntries() {
    const metrics = this.wsMetrics();
    if (!metrics?.topics) return [];
    
    return Object.entries(metrics.topics).map(([name, topicMetrics]) => ({
      name,
      metrics: topicMetrics
    }));
  }

  hasTopics(): boolean {
    const metrics = this.wsMetrics();
    return !!(metrics?.topics && Object.keys(metrics.topics).length > 0);
  }

  getConnectionBadgeVariant(): 'success' | 'warning' | 'danger' | 'neutral' {
    const totalConnections = this.wsMetrics()?.total_connections || 0;
    return totalConnections >= 1 ? 'success' : 'neutral';
  }

  getConnectionStatusText(): string {
    const totalConnections = this.wsMetrics()?.total_connections || 0;
    return totalConnections >= 1 ? 'STREAMING' : 'NO CLIENTS';
  }

  formatBandwidth(bytesPerSec: number): string {
    if (bytesPerSec >= 1024 * 1024) {
      return `${(bytesPerSec / (1024 * 1024)).toFixed(1)} MB/s`;
    } else if (bytesPerSec >= 1024) {
      return `${(bytesPerSec / 1024).toFixed(1)} KB/s`;
    } else {
      return `${bytesPerSec.toFixed(0)} B/s`;
    }
  }

  formatBytes(totalBytes: number): string {
    if (totalBytes >= 1024 * 1024 * 1024) {
      return `${(totalBytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
    } else if (totalBytes >= 1024 * 1024) {
      return `${(totalBytes / (1024 * 1024)).toFixed(1)} MB`;
    } else if (totalBytes >= 1024) {
      return `${(totalBytes / 1024).toFixed(1)} KB`;
    } else {
      return `${totalBytes} B`;
    }
  }
}