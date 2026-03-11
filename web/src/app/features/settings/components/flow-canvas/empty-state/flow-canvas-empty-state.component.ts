import {Component} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';

@Component({
  selector: 'app-flow-canvas-empty-state',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './flow-canvas-empty-state.component.html',
  styleUrl: './flow-canvas-empty-state.component.css',
})
export class FlowCanvasEmptyStateComponent {
}
