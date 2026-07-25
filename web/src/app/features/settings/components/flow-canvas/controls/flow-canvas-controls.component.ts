import {ChangeDetectionStrategy, Component, input, output, signal} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';

interface Hint {
  icon: string;
  color: string;
  key: string;
  desc: string;
}

const HINTS: Hint[] = [
  { icon: 'mouse',        color: '#2563eb', key: 'Left Click',              desc: 'Select node' },
  { icon: 'ads_click',    color: '#7c3aed', key: 'Right Click',             desc: 'Context menu' },
  { icon: 'open_with',    color: '#0891b2', key: 'Left Click Hold',         desc: 'Pan view' },
  { icon: 'select_all',   color: '#0d9488', key: 'Shift + Drag',            desc: 'Area select' },
  { icon: 'zoom_in',      color: '#ca8a04', key: 'Scroll wheel',            desc: 'Zoom' },
  { icon: 'edit',         color: '#ea580c', key: 'Double-click',            desc: 'Edit node' },
  { icon: 'content_copy', color: '#4b5563', key: 'Ctrl + C / V',            desc: 'Copy / Paste' },
  { icon: 'undo',         color: '#6b7280', key: 'Ctrl + Z',                desc: 'Undo' },
  { icon: 'redo',         color: '#6b7280', key: 'Ctrl + Y',                desc: 'Redo' },
];

export type CanvasControlAction =
  | 'fit-to-screen'
  | 'one-to-one'
  | 'snap-toggle'
  | 'minimap-toggle'
  | 'live-status-toggle'
  | 'zoom-in'
  | 'zoom-out'
  | 'undo'
  | 'redo'
  | 'reset';

/**
 * Unified floating canvas toolbar.
 * Contains zoom controls, snap-to-grid toggle, minimap toggle, and keyboard shortcuts hint.
 *
 * Emits a single `action` event with the action type — the host handles via switch.
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
  minimapVisible = input<boolean>(true);
  liveStatus = input<boolean>(true);
  canUndo = input<boolean>(false);
  canRedo = input<boolean>(false);

  action = output<CanvasControlAction>();

  readonly hints = HINTS;
  hintOpen = signal(false);
}
