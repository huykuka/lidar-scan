import { Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface Connection {
  from: string; // sensor id
  to: string; // fusion id
  path?: string; // cached path
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
}
