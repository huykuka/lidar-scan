import {ChangeDetectionStrategy, Component, input, output, signal} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';

interface Hint {
  icon: string;
  key: string;
  desc: string;
}

const HINTS: Hint[] = [
  { icon: 'mouse',        key: 'Left Click',              desc: 'Select node' },
  { icon: 'open_with',    key: 'Left Click Hold',         desc: 'Pan view' },
  { icon: 'select_all',   key: 'Shift + Left Click Hold', desc: 'Area select' },
  { icon: 'zoom_in',      key: 'Scroll wheel',            desc: 'Zoom' },
  { icon: 'edit',          key: 'Double-click',            desc: 'Edit node' },
  { icon: 'content_copy', key: 'Ctrl + C / V',            desc: 'Copy / Paste' },
  { icon: 'undo',         key: 'Ctrl + Z',                desc: 'Undo' },
  { icon: 'redo',         key: 'Ctrl + Y',                desc: 'Redo' },
];

/**
 * Unified floating canvas toolbar.
 * Contains zoom controls, snap-to-grid toggle, and keyboard shortcuts hint.
 */
@Component({
  selector: 'app-flow-canvas-controls',
  imports: [SynergyComponentsModule],
  templateUrl: './flow-canvas-controls.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './flow-canvas-controls.component.css',
})
export class FlowCanvasControlsComponent {
  zoom = input<number>(1);
  snapToGrid = input<boolean>(true);
  canUndo = input<boolean>(false);
  canRedo = input<boolean>(false);

  onFitToScreen = output<void>();
  onOneToOne = output<void>();
  onSnapToggle = output<void>();
  onZoomIn = output<void>();
  onZoomOut = output<void>();
  onUndo = output<void>();
  onRedo = output<void>();
  onReset = output<void>();

  readonly hints = HINTS;
  hintOpen = signal(false);
}
