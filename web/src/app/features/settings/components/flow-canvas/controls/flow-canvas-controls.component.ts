import {Component, input, output} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';

/**
 * Floating bottom-right canvas controls panel.
 * Displays the current zoom level and provides Reset View, Snap to Grid,
 * and +/- zoom step buttons.
 * Extracted from FlowCanvasPaletteComponent so it can live directly on the canvas
 * rather than inside the collapsible sidebar.
 */
@Component({
  selector: 'app-flow-canvas-controls',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './flow-canvas-controls.component.html',
})
export class FlowCanvasControlsComponent {
  zoom = input<number>(1);
  snapToGrid = input<boolean>(true);

  onResetView = output<void>();
  onSnapToggle = output<void>();
  onZoomIn = output<void>();
  onZoomOut = output<void>();
}
