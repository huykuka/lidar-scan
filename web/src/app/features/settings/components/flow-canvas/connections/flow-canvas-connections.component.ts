import {Component, input, output} from '@angular/core';


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
  standalone: true,
  imports: [],
  templateUrl: './flow-canvas-connections.component.html',
  styleUrl: './flow-canvas-connections.component.css',
})
export class FlowCanvasConnectionsComponent {
  connections = input.required<Connection[]>();
  pendingPath = input<string | null>(null);

  onDelete = output<string>();
}
