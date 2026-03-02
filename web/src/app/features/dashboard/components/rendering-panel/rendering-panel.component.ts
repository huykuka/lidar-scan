import { Component, input, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynCardComponent, SynBadgeComponent, SynAlertComponent } from '@synergy-design-system/angular';
import { FrontendMetricsPayload } from '../../../../core/models/metrics.model';

/**
 * Panel showing frontend Three.js rendering and WebSocket client performance metrics
 * Displays FPS, render times, long tasks, and client-side WebSocket performance
 */
@Component({
  selector: 'app-rendering-panel',
  standalone: true,
  imports: [CommonModule, SynCardComponent, SynBadgeComponent, SynAlertComponent],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './rendering-panel.component.html',
  styleUrl: './rendering-panel.component.css'
})
export class RenderingPanelComponent {
  // Signal input
  frontendMetrics = input<FrontendMetricsPayload | null>(null);

  getFpsBadgeVariant(): 'success' | 'warning' | 'danger' | 'neutral' {
    const fps = this.frontendMetrics()?.fps || 0;
    if (fps >= 55) return 'success';
    if (fps >= 30) return 'warning';
    return 'danger';
  }

  getFpsStatusText(): string {
    const fps = this.frontendMetrics()?.fps || 0;
    if (fps >= 55) return 'Excellent';
    if (fps >= 30) return 'Good';
    return 'Poor';
  }

  hasWebSocketMetrics(): boolean {
    const metrics = this.frontendMetrics();
    return !!(metrics?.ws_parse_latency_ms && Object.keys(metrics.ws_parse_latency_ms).length > 0);
  }

  getWebSocketTopics() {
    const metrics = this.frontendMetrics();
    if (!metrics) return [];

    const topics: Array<{
      name: string;
      parseLatency: number;
      framesPerSec: number;
      bytesPerSec: number;
    }> = [];

    // Combine all WebSocket metrics by topic
    Object.keys(metrics.ws_parse_latency_ms || {}).forEach(topic => {
      topics.push({
        name: topic,
        parseLatency: metrics.ws_parse_latency_ms[topic] || 0,
        framesPerSec: metrics.ws_frames_per_sec[topic] || 0,
        bytesPerSec: metrics.ws_bytes_per_sec[topic] || 0
      });
    });

    return topics;
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
}