// ML Label Legend Component
// Displays semantic class color-to-name mapping for ML segmentation

import { Component, computed, input } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface LabelLegendItem {
  class_index: number;
  class_name: string; 
  color: number[]; // RGB array
}

@Component({
  selector: 'app-ml-label-legend',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="ml-label-legend" [class.collapsed]="isCollapsed()">
      <div class="legend-header" (click)="toggleCollapsed()">
        <span class="legend-title">Semantic Classes</span>
        <span class="collapse-icon" [class.rotated]="!isCollapsed()">▼</span>
      </div>
      
      @if (!isCollapsed()) {
        <div class="legend-content">
          @for (item of legendItems(); track item.class_index) {
            <div class="legend-item">
              <div 
                class="color-swatch"
                [style.background-color]="getRgbColor(item.color)">
              </div>
              <span class="class-name">{{ item.class_name }}</span>
              <span class="class-index">[{{ item.class_index }}]</span>
            </div>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .ml-label-legend {
      position: absolute;
      top: 20px;
      right: 20px;
      background: rgba(0, 0, 0, 0.8);
      border-radius: 8px;
      padding: 12px;
      min-width: 200px;
      color: white;
      font-size: 12px;
      z-index: 1000;
    }
    
    .legend-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: pointer;
      padding: 4px 0;
    }
    
    .legend-title {
      font-weight: 600;
      font-size: 13px;
    }
    
    .collapse-icon {
      transition: transform 0.2s ease;
      font-size: 10px;
    }
    
    .collapse-icon.rotated {
      transform: rotate(-180deg);
    }
    
    .legend-content {
      margin-top: 8px;
      max-height: 300px;
      overflow-y: auto;
    }
    
    .legend-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 2px 0;
    }
    
    .color-swatch {
      width: 16px;
      height: 16px;
      border-radius: 3px;
      border: 1px solid rgba(255, 255, 255, 0.3);
      flex-shrink: 0;
    }
    
    .class-name {
      flex: 1;
      text-transform: capitalize;
    }
    
    .class-index {
      opacity: 0.7;
      font-size: 10px;
    }
    
    .collapsed .legend-content {
      display: none;
    }
  `]
})
export class MlLabelLegendComponent {
  
  // Input signals
  classNames = input<string[]>([]);
  colorMap = input<number[][]>([]);
  
  // Internal state
  private _isCollapsed = false;
  
  // Computed legend items
  legendItems = computed(() => {
    const names = this.classNames();
    const colors = this.colorMap();
    
    return names.map((name, index) => ({
      class_index: index,
      class_name: name,
      color: colors[index] || [128, 128, 128] // fallback gray
    }));
  });
  
  isCollapsed = computed(() => this._isCollapsed);
  
  toggleCollapsed(): void {
    this._isCollapsed = !this._isCollapsed;
  }
  
  getRgbColor(rgb: number[]): string {
    return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
  }
}