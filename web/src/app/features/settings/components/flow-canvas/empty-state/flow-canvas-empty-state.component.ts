import {Component, ChangeDetectionStrategy} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';

@Component({
  selector: 'app-flow-canvas-empty-state',
  imports: [SynergyComponentsModule],
  templateUrl: './flow-canvas-empty-state.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './flow-canvas-empty-state.component.css',
})
export class FlowCanvasEmptyStateComponent {}
