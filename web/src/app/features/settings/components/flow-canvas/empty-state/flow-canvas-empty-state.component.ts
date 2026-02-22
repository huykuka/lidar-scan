import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

@Component({
  selector: 'app-flow-canvas-empty-state',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './flow-canvas-empty-state.component.html',
  styleUrl: './flow-canvas-empty-state.component.css',
})
export class FlowCanvasEmptyStateComponent {}
