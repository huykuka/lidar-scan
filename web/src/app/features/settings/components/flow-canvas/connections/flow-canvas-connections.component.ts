import {Component, input, output, ChangeDetectionStrategy} from '@angular/core';


export interface Connection {
  id?: string;
  from: string;
  to: string;
  path?: string;
  color?: string; // Edge color for port-specific rendering (e.g., '#16a34a' for true, '#f97316' for false)
}

export interface PendingConnection {
  fromNodeId: string;
  path: string; // live bezier path
}

@Component({
  selector: 'app-flow-canvas-connections',
  imports: [],
  templateUrl: './flow-canvas-connections.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './flow-canvas-connections.component.css',
})
export class FlowCanvasConnectionsComponent {
  connections = input.required<Connection[]>();
  pendingPath = input<string | null>(null);
  /** Default stroke color for edges with no explicit color (overrides hardcoded hex) */
  defaultColor = input<string>('#005aff');
  /** Default flow overlay color */
  defaultFlowColor = input<string>('#80adff');

  onDelete = output<string>();
}
