import { Component, input, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynCardComponent, SynBadgeComponent } from '@synergy-design-system/angular';

/**
 * Small reusable "number + label + status badge" component
 * Used across all panels for key metrics display with consistent styling
 */
@Component({
  selector: 'app-metric-gauge',
  standalone: true,
  imports: [CommonModule, SynCardComponent, SynBadgeComponent],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './metric-gauge.component.html',
  styleUrl: './metric-gauge.component.css'
})
export class MetricGaugeComponent {
  // Required inputs
  label = input.required<string>();
  value = input.required<number | string>();
  
  // Optional inputs
  unit = input<string>('');
  status = input<'good' | 'warn' | 'bad' | 'neutral'>('neutral');
  tooltip = input<string>('');

  getBadgeVariant(): 'success' | 'warning' | 'danger' | 'neutral' {
    const statusMap = {
      good: 'success' as const,
      warn: 'warning' as const,
      bad: 'danger' as const,
      neutral: 'neutral' as const
    };
    return statusMap[this.status()];
  }

  getStatusText(): string {
    const statusTextMap = {
      good: 'Good',
      warn: 'Warning',
      bad: 'Critical',
      neutral: 'Normal'
    };
    return statusTextMap[this.status()];
  }
}