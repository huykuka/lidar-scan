import {Component, computed, CUSTOM_ELEMENTS_SCHEMA, inject, input} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {CanvasNode} from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import {NodeStatus} from '@core/models/node.model';
import {NodeCardComponent} from '@core/models/node-plugin.model';
import {CalibrationNodeStatus} from '@core/models/calibration.model';
import {NodeStoreService} from '@core/services/stores/node-store.service';

@Component({
  selector: 'app-calibration-node-card',
  standalone: true,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [SynergyComponentsModule],
  templateUrl: './calibration-node-card.component.html',
  styleUrl: './calibration-node-card.component.css',
})
export class CalibrationNodeCardComponent implements NodeCardComponent {
  node = input.required<CanvasNode>();
  status = input<NodeStatus | null>(null);
  private nodeStore = inject(NodeStoreService);

  protected calibrationStatus = computed(() => {
    return this.status() as CalibrationNodeStatus | null;
  });

  protected referenceSensorName = computed(() => {
    const refId = this.calibrationStatus()?.reference_sensor;
    if (!refId) return null;
    const allNodes = this.nodeStore.nodes();
    const refNode = allNodes.find((n) => n.id === refId);
    return refNode?.name || refId;
  });

  protected sourceSensorCount = computed(() => {
    const sources = this.calibrationStatus()?.source_sensors || [];
    return sources.length;
  });

  protected bufferedFrameCount = computed(() => {
    const buffered = this.calibrationStatus()?.buffered_frames;
    if (!buffered) return 0;
    // New dict format: { sensorId: frameCount } — sum all frame counts
    if (!Array.isArray(buffered)) {
      return Object.values(buffered as Record<string, number>).reduce((sum, n) => sum + n, 0);
    }
    // Legacy array format: array of sensor IDs
    return buffered.length;
  });

  /** Per-sensor buffered frame entries for detailed display */
  protected bufferedFrameEntries = computed(() => {
    const buffered = this.calibrationStatus()?.buffered_frames;
    if (!buffered) return [];
    if (!Array.isArray(buffered)) {
      return Object.entries(buffered as Record<string, number>).map(([sensorId, count]) => ({sensorId, count}));
    }
    return buffered.map((sensorId: string) => ({sensorId, count: 1}));
  });

  protected hasPendingCalibration = computed(() => {
    return this.calibrationStatus()?.has_pending || false;
  });

  protected pendingResultsCount = computed(() => {
    const pending = this.calibrationStatus()?.pending_results || {};
    return Object.keys(pending).length;
  });

  protected lastCalibrationTime = computed(() => {
    const time = this.calibrationStatus()?.last_calibration_time;
    if (!time) return null;
    const date = new Date(time);
    return date.toLocaleString();
  });

  protected sampleFrames = computed(() => {
    return this.node().data.config['sample_frames'] || 10;
  });
}
