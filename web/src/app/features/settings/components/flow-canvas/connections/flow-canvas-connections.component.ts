import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface Connection {
  id?: string;
  from: string;
  to: string;
  path?: string;
}

export interface PendingConnection {
  fromNodeId: string;
  path: string; // live bezier path
}

@Component({
  selector: 'app-flow-canvas-connections',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './flow-canvas-connections.component.html',
  styleUrl: './flow-canvas-connections.component.css',
})
export class FlowCanvasConnectionsComponent {
  connections = input.required<Connection[]>();
  pendingPath = input<string | null>(null);

  onDelete = output<string>();
}
