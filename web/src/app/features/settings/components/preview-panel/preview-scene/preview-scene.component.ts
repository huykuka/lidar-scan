import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  effect,
  input,
  output,
  signal,
  viewChildren,
} from '@angular/core';
import { NgtsPointsBuffer } from 'angular-three-soba/performances';
import { NgtsPivotControls } from 'angular-three-soba/gizmos';
import * as THREE from 'three';

export interface PreviewSceneEntry {
  topic: string;
  color: string;
  pointSize: number;
  buf: Float32Array;
  initialOffset: [number, number, number];
  initialRotation: [number, number, number];
}

@Component({
  selector: 'app-preview-scene',
  templateUrl: './preview-scene.component.html',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [NgtsPointsBuffer, NgtsPivotControls],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PreviewSceneComponent {
  readonly entries = input.required<PreviewSceneEntry[]>();
  readonly showGizmos = input.required<boolean>();
  readonly frames = input.required<Map<string, { points: Float32Array; count: number }>>();
  readonly maxPoints = input(250_000);

  readonly dragged = output<{ topic: string; event: any }>();
  readonly dragEnded = output<string>();

  /** Tracks which topic is currently being dragged */
  protected readonly draggingTopic = signal<string | null>(null);
  readonly isDragging = input<boolean>(false);

  private readonly pointsBuffers = viewChildren<NgtsPointsBuffer>('buf');

  constructor() {
    effect(() => {
      const entries = this.entries();
      const frames = this.frames();
      const bufs = this.pointsBuffers();
      const max = this.maxPoints();

      entries.forEach((entry, i) => {
        const points = bufs[i]?.pointsRef()?.nativeElement;
        if (!points) return;

        const frame = frames.get(entry.topic) ?? null;
        if (!frame || frame.count === 0) {
          points.visible = false;
          return;
        }
        points.visible = true;

        const count = Math.min(frame.count, max);
        entry.buf.set(frame.points.subarray(0, count * 3));

        const geo = points.geometry;
        if (!geo) return;
        geo.setDrawRange(0, count);
        const attr = geo.attributes['position'];
        if (attr) attr.needsUpdate = true;
      });
    });
  }

  onDragStart(topic: string): void {
    this.draggingTopic.set(topic);
  }

  onDragEnd(topic: string): void {
    this.draggingTopic.set(null);
    this.dragEnded.emit(topic);
  }
}
