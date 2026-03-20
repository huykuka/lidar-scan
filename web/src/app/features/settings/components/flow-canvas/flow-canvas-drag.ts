import {Injectable, signal} from '@angular/core';
import {CanvasNode} from './node/flow-canvas-node.component';

export interface DragPosition {
  x: number;
  y: number;
}

@Injectable()
export class FlowCanvasDragService {
  readonly draggingNode = signal<CanvasNode | null>(null);
  readonly dragOffset = signal<DragPosition>({x: 0, y: 0});

  readonly paletteDragType = signal<string | null>(null);

  readonly pendingConnection = signal<{
    fromNodeId: string;
    fromPortId: string;
    fromPortIndex: number;
    cursorX: number;
    cursorY: number;
  } | null>(null);
  readonly pendingPath = signal<string | null>(null);

  readonly isPanning = signal(false);


  startNodeDrag(node: CanvasNode, offsetX: number, offsetY: number): void {
    this.draggingNode.set(node);
    this.dragOffset.set({x: offsetX, y: offsetY});
  }

  updateDraggingNode(node: CanvasNode): void {
    this.draggingNode.set(node);
  }

  endNodeDrag(): { nodeId: string; position: DragPosition } | null {
    const node = this.draggingNode();
    if (!node) return null;
    const result = {nodeId: node.id, position: {...node.position}};
    this.draggingNode.set(null);
    return result;
  }

  startPaletteDrag(type: string, event: DragEvent): void {
    this.paletteDragType.set(type);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'copy';
      event.dataTransfer.setData('text/plain', type);
    }
  }

  endPaletteDrag(): void {
    this.paletteDragType.set(null);
  }

  startConnectionDrag(fromNodeId: string, fromPortId: string = 'out', fromPortIndex: number = 0): void {
    this.pendingConnection.set({fromNodeId, fromPortId, fromPortIndex, cursorX: 0, cursorY: 0});
  }

  updateConnectionPath(path: string): void {
    this.pendingPath.set(path);
  }

  cancelConnectionDrag(): void {
    this.pendingConnection.set(null);
    this.pendingPath.set(null);
  }

  startPan(): void {
    this.isPanning.set(true);
  }

  endPan(): void {
    this.isPanning.set(false);
  }
}
