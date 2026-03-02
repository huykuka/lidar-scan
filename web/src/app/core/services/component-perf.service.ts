import { Injectable } from '@angular/core';
import { MetricsStoreService } from './stores/metrics-store.service';

/**
 * Passive service using Web PerformanceObserver API to detect long tasks
 * Tracks main-thread blocks >50ms and pushes counts/durations to MetricsStore
 */
@Injectable({
  providedIn: 'root',
})
export class ComponentPerfService {
  private observer: PerformanceObserver | null = null;
  private flushInterval: any = null;
  private longTaskAccumulator = { count: 0, totalMs: 0 };

  constructor(private metricsStore: MetricsStoreService) {}

  /**
   * Starts observing long tasks using PerformanceObserver API
   */
  startObserving(): void {
    if (this.observer) {
      return; // Already observing
    }

    try {
      // Check if PerformanceObserver is available (graceful degradation for older browsers)
      if (typeof PerformanceObserver === 'undefined') {
        console.warn('[ComponentPerf] PerformanceObserver not available - long task monitoring disabled');
        return;
      }

      // Create observer for long tasks (>50ms main thread blocks)
      this.observer = new PerformanceObserver((entryList) => {
        const entries = entryList.getEntries();
        
        entries.forEach((entry) => {
          if (entry.entryType === 'longtask') {
            this.longTaskAccumulator.count++;
            this.longTaskAccumulator.totalMs += entry.duration;
          }
        });
      });

      // Observe long task entries
      this.observer.observe({ entryTypes: ['longtask'] });
      console.log('[ComponentPerf] Started observing long tasks');

      // Set up 1-second flush interval to update MetricsStore
      this.flushInterval = setInterval(() => {
        this.flushAccumulatedMetrics();
      }, 1000);

    } catch (error) {
      console.warn('[ComponentPerf] Failed to start PerformanceObserver:', error);
      // Graceful degradation - continue without long task monitoring
    }
  }

  /**
   * Stops observing long tasks and clears interval
   */
  stopObserving(): void {
    if (this.observer) {
      this.observer.disconnect();
      this.observer = null;
      console.log('[ComponentPerf] Stopped observing long tasks');
    }

    if (this.flushInterval) {
      clearInterval(this.flushInterval);
      this.flushInterval = null;
    }

    // Reset accumulator
    this.longTaskAccumulator = { count: 0, totalMs: 0 };
  }

  /**
   * Flushes accumulated long task metrics to MetricsStore
   * Only updates the long_task_count and long_task_total_ms fields
   */
  private flushAccumulatedMetrics(): void {
    if (this.longTaskAccumulator.count > 0 || this.longTaskAccumulator.totalMs > 0) {
      // Partial update - only update long task fields in existing frontend metrics
      this.metricsStore.updateFrontend({
        long_task_count: this.longTaskAccumulator.count,
        long_task_total_ms: this.longTaskAccumulator.totalMs
      });

      // Reset accumulator for next window
      this.longTaskAccumulator = { count: 0, totalMs: 0 };
    }
  }
}