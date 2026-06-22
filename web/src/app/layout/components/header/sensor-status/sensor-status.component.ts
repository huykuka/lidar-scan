import { Component, computed, inject, ChangeDetectionStrategy } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeStoreService } from '@core/services/stores';

/**
 * Sensor-node health indicator.
 * Icons: sick2025 iconset — `sensors` (outline, all OK) / `sensors_off` (errors present).
 * Size: large — syn-icon-button size="large".
 * Icon AND badge color both reflect health state via --status-color CSS variable.
 */
@Component({
  selector: 'app-sensor-status',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './sensor-status.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host {
      display: inline-flex;
      position: relative;
      align-items: center;
    }
    syn-icon-button {
      color: var(--status-color);
    }
  `,
})
export class SensorStatusComponent {
  private readonly store = inject(NodeStoreService);

  private readonly sensorNodes = computed(() =>
    this.store.nodes().filter((n) => n.category === 'sensor'),
  );

  private readonly statusMap = this.store.nodeStatusMap;

  protected readonly count = computed(() => this.sensorNodes().length);

  protected readonly errorCount = computed(() => {
    const map = this.statusMap();
    return this.sensorNodes().filter((n) => map.get(n.id)?.operational_state === 'ERROR').length;
  });

  /** true = all OK, false = some errors, null = no sensors configured */
  protected readonly health = computed<boolean | null>(() => {
    if (this.count() === 0) return null;
    return this.errorCount() === 0;
  });

  /** sick2025 icons confirmed via Synergy MCP — sensors (outline) / sensors_off */
  protected readonly icon = computed(() => {
    const h = this.health();
    if (h === false) return 'sensors_off';
    return 'sensors';
  });

  protected readonly label = computed(() => {
    const total = this.count();
    if (total === 0) return 'No sensor nodes configured';
    const errors = this.errorCount();
    if (errors === 0) return `${total} sensor${total > 1 ? 's' : ''} — all OK`;
    return `${total} sensor${total > 1 ? 's' : ''} — ${errors} in ERROR`;
  });

  /** Synergy CSS token for icon + badge color, reflecting health state */
  protected readonly statusColor = computed(() => {
    const h = this.health();
    if (h === null) return 'var(--syn-color-neutral-500)';
    return h ? 'var(--syn-color-success-600)' : 'var(--syn-color-error-600)';
  });

  /** Synergy CSS token for badge background — same as statusColor */
  protected readonly badgeColor = computed(() => this.statusColor());
}
