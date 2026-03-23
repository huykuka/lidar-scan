import {Component, computed, input} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';

/**
 * Dumb presentational component: renders a metadata object as a table.
 * Shows an empty state while waiting for the first WebSocket message.
 */
@Component({
  selector: 'app-metadata-table',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './metadata-table.component.html',
})
export class MetadataTableComponent {
  metadata = input<Record<string, any> | null>(null);

  /** Flattened key-value entries for `@for` iteration. */
  protected entries = computed(() => Object.entries(this.metadata() ?? {}));

  /**
   * Render a metadata value as a human-readable string.
   */
  protected renderValue(value: unknown): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    return String(value);
  }

  /**
   * Return the display type label for a value.
   */
  protected typeLabel(value: unknown): string {
    if (value === null) return 'null';
    if (Array.isArray(value)) return 'array';
    return typeof value;
  }

  /**
   * Whether a value should be rendered inside a <pre> block (objects/arrays).
   */
  protected isComplex(value: unknown): boolean {
    return value !== null && typeof value === 'object';
  }
}
