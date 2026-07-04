import {ChangeDetectionStrategy, Component, computed, input, signal} from '@angular/core';

@Component({
  selector: 'app-metadata-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [],
  templateUrl: './metadata-table.component.html',
  styleUrl: './metadata-table.component.css',
})
export class MetadataTableComponent {
  metadata = input<Record<string, unknown>>({});

  /** Track which nested keys are expanded */
  protected expandedKeys = signal<Set<string>>(new Set());

  protected rows = computed(() => {
    return Object.entries(this.metadata()).map(([key, value]) => ({
      key,
      value,
      isComplex: this.isComplex(value),
      displayValue: this.displayValue(value),
    }));
  });

  protected isComplex(value: unknown): boolean {
    return value !== null && typeof value === 'object';
  }

  protected displayValue(value: unknown): string {
    if (value === null) return 'null';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'number') return value.toFixed(3);
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }

  protected isExpanded(key: string): boolean {
    return this.expandedKeys().has(key);
  }

  protected toggleExpand(key: string): void {
    const current = new Set(this.expandedKeys());
    if (current.has(key)) {
      current.delete(key);
    } else {
      current.add(key);
    }
    this.expandedKeys.set(current);
  }
}
